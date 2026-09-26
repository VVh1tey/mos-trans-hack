export type FavoriteRoute = { id: string; number: string };
export const FAVORITES_KEY = 'favorite-routes';

export function readFavorites(): FavoriteRoute[] {
  try {
    const saved = localStorage.getItem(FAVORITES_KEY);
    const legacy = localStorage.getItem('pinned-route');
    const values: unknown = saved !== null ? JSON.parse(saved) : legacy ? [JSON.parse(legacy)] : [];
    if (!Array.isArray(values)) return [];
    const seen = new Set<string>();
    return values.filter((item): item is FavoriteRoute => {
      if (!item || typeof item.id !== 'string' || typeof item.number !== 'string' || seen.has(item.id)) return false;
      seen.add(item.id);
      return true;
    });
  } catch { return []; }
}
