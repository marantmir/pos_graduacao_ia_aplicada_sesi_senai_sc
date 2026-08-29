import { api } from "./client.js";

/**
 * Checks whether a team name already exists (local base or saved online
 * profile). If it does, returns the resolved ref so callers can select it
 * directly. If it does not, returns the online search result so the caller
 * can offer "cadastrar" as the next step instead of jumping into analysis.
 */
export async function findExistingTeamByName(name) {
  const cleaned = (name || "").trim();
  if (!cleaned) {
    throw new Error("Informe o nome do time.");
  }

  const localTeams = await api.teams();
  const localMatch = localTeams.find((team) => team.name.toLowerCase() === cleaned.toLowerCase());
  if (localMatch) {
    return { found: true, ref: String(localMatch.id), name: localMatch.name };
  }

  const online = await api.onlineTeamSearch(cleaned);
  if (online.saved && online.profile) {
    return { found: true, ref: `online-${online.profile.online_profile_id}`, name: online.profile.name };
  }

  return { found: false, name: cleaned, online };
}

/** Registers (saves) a team found only via online search, so it becomes a
 * selectable/searchable option across the app from now on. */
export async function registerTeamFromOnlineSearch(name, online) {
  const profile = online?.profile || {};
  const saved = await api.saveOnlineProfile({
    team_name: name,
    country: profile.country,
    league: profile.league,
    coach: profile.coach,
    base_formation: profile.base_formation,
    style: profile.style,
    confidence: profile.confidence,
    status: "Fonte tática salva",
    online_search: online?.online_search
  });
  return { ref: `online-${saved.online_profile_id}`, name: saved.name };
}
