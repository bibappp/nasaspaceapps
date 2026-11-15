// Leaflet-Geoman обращается к глобальному L, поэтому выставляем его до импорта Geoman.
import L from "leaflet";

declare global {
  interface Window {
    L: typeof L;
  }
}
window.L = L;
export default L;
