const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response, "Falha na requisicao"));
  }

  return response.json();
}

function formatApiError(payload) {
  if (typeof payload?.detail === "string") {
    return payload.detail;
  }

  if (Array.isArray(payload?.detail)) {
    return payload.detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .join(" ");
  }

  return payload?.message || "Falha na requisicao";
}

async function readErrorMessage(response, fallback) {
  const contentType = response.headers.get("Content-Type") || "";
  if (contentType.includes("application/json")) {
    try {
      return formatApiError(await response.json());
    } catch {
      return fallback;
    }
  }

  let text = "";
  try {
    text = await response.text();
  } catch {
    text = "";
  }

  if (response.status === 502 || response.status === 504 || /<title>\s*50[24]\s*<\/title>/i.test(text)) {
    return (
      "O servidor interrompeu o processamento do video antes de concluir. " +
      "Tente enviar um recorte menor, reduzir os frames analisados ou aumentar o intervalo entre frames."
    );
  }

  const cleaned = stripHtml(text).trim();
  if (!cleaned) return fallback;
  return cleaned.length > 320 ? `${cleaned.slice(0, 320)}...` : cleaned;
}

function stripHtml(value) {
  return String(value || "")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
}

export const api = {
  health: () => request("/api/health"),
  teams: () => request("/api/teams"),
  teamOptions: () => request("/api/teams/options"),
  teamWorkspace: (teamRef) => request(`/api/teams/workspace/${encodeURIComponent(teamRef)}`),
  coachInsights: (teamRef, perspective = "opponent", gameState = "balanced") =>
    request(
      `/api/teams/workspace/${encodeURIComponent(teamRef)}/coach-insights?perspective=${encodeURIComponent(
        perspective
      )}&game_state=${encodeURIComponent(gameState)}`
    ),
  searchTeams: (query, category = "") =>
    request(
      `/api/teams/search?query=${encodeURIComponent(query)}${category ? `&category=${encodeURIComponent(category)}` : ""}`
    ),
  onlineTeamSearch: (name) => request(`/api/teams/online-search?name=${encodeURIComponent(name)}`),
  onlineProfiles: (query = "") => request(`/api/teams/online-profiles?query=${encodeURIComponent(query)}`),
  saveOnlineProfile: (payload) =>
    request("/api/teams/online-profiles", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  ownTeam: () => request("/api/teams/own-team"),
  setOwnTeam: (ref) =>
    request("/api/teams/own-team", {
      method: "PUT",
      body: JSON.stringify({ ref })
    }),
  team: (teamId) => request(`/api/teams/${teamId}`),
  tacticalAnalysis: (teamId) => request(`/api/teams/${teamId}/tactical-analysis`),
  formations: (teamId) => request(`/api/teams/${teamId}/formations`),
  players: (teamId) => request(`/api/teams/${teamId}/players`),
  sources: (teamId) => request(`/api/teams/${teamId}/sources`),
  graphAnalysis: (teamId) => request(`/api/teams/${teamId}/graph-analysis`),
  operationalResearch: (teamId, formation = "") =>
    request(
      `/api/teams/${teamId}/operational-research${formation ? `?formation=${encodeURIComponent(formation)}` : ""}`
    ),
  uploadVideoVision: async (teamRef, file, options = {}) => {
    const maxUploadBytes = 300 * 1024 * 1024;
    if (file.size > maxUploadBytes) {
      throw new Error("Vídeo excede o limite de 300MB. Envie um recorte menor para a análise visual.");
    }
    const formData = new FormData();
    formData.append("file", file);
    (options.jerseyFiles || []).forEach((jerseyFile) => {
      formData.append("jersey_refs", jerseyFile);
    });
    const params = new URLSearchParams();
    if (options.maxFrames) params.set("max_frames", options.maxFrames);
    if (options.sampleEvery) params.set("sample_every", options.sampleEvery);
    if (options.teamFilter) params.set("team_filter", options.teamFilter);
    if (!/^\d+$/.test(String(teamRef)) && options.teamName) {
      params.set("team_name", options.teamName);
    }
    const query = params.toString() ? `?${params.toString()}` : "";
    const uploadPath = /^\d+$/.test(String(teamRef))
      ? `/api/teams/${teamRef}/video-vision/upload${query}`
      : `/api/teams/video-vision/upload${query}`;
    const response = await fetch(`${API_BASE}${uploadPath}`, {
      method: "POST",
      body: formData
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response, "Falha ao processar o video"));
    }
    return response.json();
  },
  uploadVideoVisionWithProgress: async (teamRef, file, options = {}, onProgress) => {
    const maxUploadBytes = 300 * 1024 * 1024;
    if (file.size > maxUploadBytes) {
      throw new Error("Vídeo excede o limite de 300MB. Envie um recorte menor para a análise visual.");
    }
    const formData = new FormData();
    formData.append("file", file);
    (options.jerseyFiles || []).forEach((jerseyFile) => {
      formData.append("jersey_refs", jerseyFile);
    });
    const params = new URLSearchParams();
    if (options.maxFrames) params.set("max_frames", options.maxFrames);
    if (options.sampleEvery) params.set("sample_every", options.sampleEvery);
    if (options.teamFilter) params.set("team_filter", options.teamFilter);
    if (!/^\d+$/.test(String(teamRef)) && options.teamName) {
      params.set("team_name", options.teamName);
    }
    const query = params.toString() ? `?${params.toString()}` : "";
    const startPath = /^\d+$/.test(String(teamRef))
      ? `/api/teams/${teamRef}/video-vision/jobs${query}`
      : `/api/teams/video-vision/jobs${query}`;

    const startResponse = await fetch(`${API_BASE}${startPath}`, {
      method: "POST",
      body: formData
    });
    if (!startResponse.ok) {
      throw new Error(await readErrorMessage(startResponse, "Falha ao iniciar o processamento do video"));
    }
    const { job_id: jobId } = await startResponse.json();

    return new Promise((resolve, reject) => {
      const maxReconnects = 4;
      let reconnects = 0;
      let settled = false;

      const connect = () => {
        const source = new EventSource(`${API_BASE}/api/teams/video-vision/jobs/${jobId}/events`);
        source.onmessage = (event) => {
          let payload;
          try {
            payload = JSON.parse(event.data);
          } catch {
            return;
          }
          reconnects = 0;
          if (payload.status === "processing") {
            onProgress?.(payload);
          } else if (payload.status === "done") {
            settled = true;
            source.close();
            resolve(payload.result);
          } else {
            settled = true;
            source.close();
            reject(new Error(payload.message || "Falha ao processar o video."));
          }
        };
        source.onerror = () => {
          source.close();
          if (settled) return;
          reconnects += 1;
          if (reconnects > maxReconnects) {
            reject(new Error("Conexão de progresso do processamento foi perdida. Tente novamente."));
            return;
          }
          // O backend retém o resultado do job por alguns minutos, então a
          // reconexão ainda recebe o "done" mesmo se a conexão caiu no final.
          setTimeout(connect, 1000 * reconnects);
        };
      };

      connect();
    });
  },
  collectSources: (payload) =>
    request("/api/teams/sources/collect", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  saveDetectedFormation: (teamId, payload) =>
    request(`/api/teams/${teamId}/formations/detected`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  publicIntelligence: (teamId) => request(`/api/teams/${teamId}/public-intelligence`),
  gamePlan: (teamId) => request(`/api/teams/${teamId}/game-plan`),
  previewAnalysis: (payload) =>
    request("/api/analysis/preview", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  createAnalysis: (payload) =>
    request("/api/analysis", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  history: () => request("/api/history"),
  llmConfig: () => request("/api/llm/config"),
  saveLlmConfig: (payload) =>
    request("/api/llm/config", {
      method: "PUT",
      body: JSON.stringify(payload)
    }),
  testLlmConfig: () =>
    request("/api/llm/test", {
      method: "POST",
      body: JSON.stringify({})
    }),
  generateReport: (payload) =>
    request("/api/reports", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  adminMeta: () => request("/api/admin/meta", { headers: adminHeaders() }),
  adminUsers: () => request("/api/admin/users", { headers: adminHeaders() }),
  adminCreateUser: (payload) =>
    request("/api/admin/users", { method: "POST", body: JSON.stringify(payload), headers: adminHeaders() }),
  adminUpdateUser: (id, payload) =>
    request(`/api/admin/users/${id}`, { method: "PUT", body: JSON.stringify(payload), headers: adminHeaders() }),
  adminDeleteUser: (id) => request(`/api/admin/users/${id}`, { method: "DELETE", headers: adminHeaders() }),
  adminList: (collection) => request(`/api/admin/collections/${collection}`, { headers: adminHeaders() }),
  adminCreate: (collection, payload) =>
    request(`/api/admin/collections/${collection}`, {
      method: "POST",
      body: JSON.stringify(payload),
      headers: adminHeaders()
    }),
  adminUpdate: (collection, id, payload) =>
    request(`/api/admin/collections/${collection}/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
      headers: adminHeaders()
    }),
  adminDelete: (collection, id) =>
    request(`/api/admin/collections/${collection}/${id}`, { method: "DELETE", headers: adminHeaders() })
};

// Em deploys com FOOTBALL_INTEL_ADMIN_TOKEN definido no backend, o token informado pelo
// administrador fica no localStorage e segue em todas as chamadas de admin.
// Sem token salvo (uso local), nenhum header extra é enviado.
function adminHeaders() {
  let token = "";
  try {
    token = window.localStorage.getItem("football_intel_admin_token") || "";
  } catch {
    token = "";
  }
  return token ? { "X-Admin-Token": token } : {};
}
