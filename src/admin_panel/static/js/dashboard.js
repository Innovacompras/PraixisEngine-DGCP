// Dashboard view — health checks, system stats, GPU status.
function _adminDashboard() {
  return {

    async loadDashboard() {
      this.loading.dashboard = true;
      await Promise.all([this.loadStats(), this.loadGpu()]);
      this.loading.dashboard = false;
      this.dashboardLoaded   = true;
      this.loadHealth();
    },

    async loadHealth() {
      this.health.redis    = null;
      this.health.chromadb = null;
      this.health.llm      = null;
      const load = async (svc) => {
        try {
          const r = await this.req('GET', '/api/system/health/' + svc);
          this.health[svc] = r.ok ? (await r.json()).status : 'offline';
        } catch { this.health[svc] = 'offline'; }
      };
      await Promise.all([load('redis'), load('chromadb'), load('llm')]);
    },

    async loadStats() {
      try {
        const r = await this.req('GET', '/api/system/stats');
        if (r.ok) this.stats = await r.json();
      } catch {}
    },

    async loadGpu() {
      try {
        const r = await this.req('GET', '/api/system/gpu');
        if (r.ok) this.gpu = await r.json();
      } catch {}
    },

    gpuBarWidth() {
      if (!this.gpu.slots_total) return '0%';
      return Math.min(100, Math.round((this.gpu.slots_in_use / this.gpu.slots_total) * 100)) + '%';
    },

    gpuBarColor() {
      if (!this.gpu.slots_total) return 'bg-slate-600';
      const pct = this.gpu.slots_in_use / this.gpu.slots_total;
      if (pct < 0.5)  return 'bg-green-500';
      if (pct < 0.85) return 'bg-amber-500';
      return 'bg-red-500';
    },

  };
}
