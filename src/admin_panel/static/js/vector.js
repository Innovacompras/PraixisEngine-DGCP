// Vector DB view — collection management, file drill-down, semantic search.
function _adminVector() {
  return {

    get vectorSearchApps() {
      return [...new Set(this.vectorCollections.map(c => c.app_name))].sort();
    },

    get vectorSearchFilteredCollections() {
      if (!this.vectorSearch.appName) return [];
      return this.vectorCollections
        .filter(c => c.app_name === this.vectorSearch.appName)
        .map(c => c.collection_name)
        .sort();
    },

    async loadVectorCollections() {
      this.loading.vector = true;
      try {
        const r = await this.req('GET', '/api/system/vector/collections');
        if (r.ok) {
          const d = await r.json();
          this.vectorCollections = d.collections || [];
          this.vectorLoaded      = true;
        }
      } finally {
        this.loading.vector = false;
      }
    },

    vectorKey(col) {
      return col.app_name + '::' + col.collection_name;
    },

    vectorTotalChunks() {
      return this.vectorCollections.reduce((s, c) => s + (c.chunk_count || 0), 0);
    },

    async toggleFiles(col) {
      const key = this.vectorKey(col);
      if (this.vectorExpanded === key) { this.vectorExpanded = null; return; }
      this.vectorExpanded = key;
      if (this.vectorFiles[key] !== undefined) return;
      this.vectorFilesLoading[key] = true;
      try {
        const r = await this.req('GET',
          '/api/system/vector/collections/' +
          encodeURIComponent(col.app_name) + '/' +
          encodeURIComponent(col.collection_name) + '/files');
        this.vectorFiles[key] = r.ok ? (await r.json()).files || [] : [];
      } catch {
        this.vectorFiles[key] = [];
      } finally {
        this.vectorFilesLoading[key] = false;
      }
    },

    openDeleteCollectionModal(col) {
      this.modalData    = col;
      this.modalLoading = false;
      this.modal        = 'deleteCollection';
    },

    async deleteCollection() {
      this.modalLoading = true;
      try {
        const col = this.modalData;
        const r   = await this.req('DELETE',
          '/api/system/vector/collections/' +
          encodeURIComponent(col.app_name) + '/' +
          encodeURIComponent(col.collection_name));
        if (r.ok) {
          const key = this.vectorKey(col);
          this.vectorCollections = this.vectorCollections.filter(c => this.vectorKey(c) !== key);
          delete this.vectorFiles[key];
          if (this.vectorExpanded === key) this.vectorExpanded = null;
          this.showToast(`Collection "${col.collection_name}" deleted.`, 'success');
        } else {
          const d = await r.json().catch(() => ({}));
          this.showToast(d.detail || 'Delete failed.', 'error');
        }
      } finally {
        this.modalLoading = false;
        this.modal        = null;
      }
    },

    openDeleteFileModal(col, filename) {
      this.modalData    = { ...col, filename };
      this.modalLoading = false;
      this.modal        = 'deleteFile';
    },

    async deleteFile() {
      this.modalLoading = true;
      try {
        const { app_name, collection_name, filename } = this.modalData;
        const r = await this.req('DELETE',
          '/api/system/vector/collections/' +
          encodeURIComponent(app_name) + '/' +
          encodeURIComponent(collection_name) + '/files',
          { filename });
        if (r.ok) {
          const key = app_name + '::' + collection_name;
          if (this.vectorFiles[key]) {
            this.vectorFiles[key] = this.vectorFiles[key].filter(f => f !== filename);
          }
          // A file owns an unknown number of chunks, so re-fetch collections
          // for an accurate chunk count instead of guessing.
          await this.loadVectorCollections();
          this.showToast(`"${filename}" deleted.`, 'success');
        } else {
          const d = await r.json().catch(() => ({}));
          this.showToast(d.detail || 'Delete failed.', 'error');
        }
      } finally {
        this.modalLoading = false;
        this.modal        = null;
      }
    },

    async runVectorSearch() {
      const { appName, collection, query, nResults } = this.vectorSearch;
      if (!appName || !collection || !query.trim()) return;
      this.vectorSearch.loading  = true;
      this.vectorSearch.done     = false;
      this.vectorSearch.results  = [];
      this.vectorSearch.expanded = {};
      try {
        const r = await this.req('GET', '/api/system/vector/search', {
          app_name:        appName,
          collection_name: collection,
          query:           query.trim(),
          n_results:       nResults,
        });
        if (r.ok) {
          this.vectorSearch.results = (await r.json()).results || [];
        } else {
          const d = await r.json().catch(() => ({}));
          this.showToast(d.detail || 'Search failed.', 'error');
        }
      } catch {
        this.showToast('Search request failed.', 'error');
      } finally {
        this.vectorSearch.loading = false;
        this.vectorSearch.done    = true;
      }
    },

    // RRF score = 1/(60+rank_sem) + 1/(60+rank_fts). Max ≈ 2/61 ≈ 0.0328 when a
    // chunk ranks #1 in both. ~0.0164 when it tops only one source. Thresholds
    // are calibrated against those endpoints, not cosine similarity.
    scoreColor(score) {
      if (score >= 0.025) return 'bg-green-400/15 text-green-400 ring-green-500/20';
      if (score >= 0.012) return 'bg-amber-400/15 text-amber-400 ring-amber-500/20';
      return 'bg-red-400/15 text-red-400 ring-red-500/20';
    },

  };
}
