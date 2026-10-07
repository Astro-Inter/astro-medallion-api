// Cloudflare adapter only. API endpoints, auth and PostgreSQL queries run
// in the Python/FastAPI container defined by Dockerfile.
import { DurableObject } from 'cloudflare:workers';

export class FastApiContainer extends DurableObject {
  starting;

  async startAndWait() {
    const container = this.ctx.container;
    if (!this.env.API_TOKEN || !this.env.DATABASE_URL) throw new Error('Missing secrets');
    if (!container.running) {
      container.start({
        image: container.images.base, instance: 'lite', enableInternet: true,
        env: { API_TOKEN: this.env.API_TOKEN, DATABASE_URL: this.env.DATABASE_URL,
          DATABASE_SSL_CA: this.env.DATABASE_SSL_CA ?? '' },
      });
    }
    await container.setInactivityTimeout(5 * 60 * 1000);
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        const response = await container.getTcpPort(8080).fetch('http://container/health', {
          headers: { Authorization: `Bearer ${this.env.API_TOKEN}` },
          signal: AbortSignal.timeout(1000),
        });
        await response.body?.cancel();
        if (response.ok) return;
      } catch { /* Retry until Uvicorn is ready. */ }
      await scheduler.wait(200);
    }
    throw new Error('Container not ready');
  }

  async fetch(request) {
    this.starting ??= this.startAndWait().finally(() => { this.starting = undefined; });
    await this.starting;
    const url = new URL(request.url);
    url.protocol = 'http:';
    url.host = 'container';
    const forwarded = new Request(url, request);
    forwarded.headers.delete('host');
    return this.ctx.container.getTcpPort(8080).fetch(forwarded);
  }
}

export default {
  async fetch(request, env) {
    try {
      return await env.FASTAPI.getByName('astro-medallion-api').fetch(request);
    } catch {
      return Response.json({ error: { code: 'container_unavailable', message: 'Serviço temporariamente indisponível.' } },
        { status: 503, headers: { 'Cache-Control': 'no-store' } });
    }
  },
};
