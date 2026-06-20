/* ============================================================
   Design tokens — single source of truth.
   Extracted from the "Run Workspace" design prototype
   (design/run-workspace/styles.css). The prototype authors
   tokens in oklch; they are converted here to sRGB hex so the
   existing inline-style `${color}NN` alpha-suffix pattern keeps
   working unchanged.

   THEMES drives the live React inline styles. cssVars() emits the
   same palette as CSS custom properties on :root / [data-theme]
   so class-based / var()-based styling shares one source.
   ============================================================ */

export const FONT_SANS = "'IBM Plex Sans',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";
export const FONT_MONO = "'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace";

export const RADII = { sm: 5, md: 8, lg: 11, xl: 14 };

/* Accent presets — user-selectable in Settings. Each overrides only the
   accent-family tokens (accent / hover / soft / text-on / start-hover) on top
   of the active light|dark theme, so the rest of the palette is unchanged.
   "graphite" mirrors the THEMES defaults below. swatch is for the picker UI. */
export const ACCENTS = {
  graphite: {
    label: "Graphite", swatch: "#6b7785",
    light: { accent: "#4f5964", accentHover: "#3c4651", accentSoft: "#e6f0fa", accentTextOn: "#fcfcfd", startHoverBg: "#e6f0fa" },
    dark:  { accent: "#97a7b8", accentHover: "#acbdce", accentSoft: "#242f3b", accentTextOn: "#15171a", startHoverBg: "#242f3b" },
  },
  slate: {
    label: "Slate", swatch: "#3b6fb0",
    light: { accent: "#3b6fb0", accentHover: "#2f5b92", accentSoft: "#e6eef9", accentTextOn: "#ffffff", startHoverBg: "#e6eef9" },
    dark:  { accent: "#6f9fd8", accentHover: "#88b2e4", accentSoft: "#1c2a3b", accentTextOn: "#0c1116", startHoverBg: "#1c2a3b" },
  },
  teal: {
    label: "Teal", swatch: "#1f8a7a",
    light: { accent: "#1f8a7a", accentHover: "#176c60", accentSoft: "#e0f3ef", accentTextOn: "#ffffff", startHoverBg: "#e0f3ef" },
    dark:  { accent: "#4fc4ae", accentHover: "#6fd4c0", accentSoft: "#0e2f2a", accentTextOn: "#08110f", startHoverBg: "#0e2f2a" },
  },
  indigo: {
    label: "Indigo", swatch: "#5a57d6",
    light: { accent: "#5a57d6", accentHover: "#4744bb", accentSoft: "#ebebfb", accentTextOn: "#ffffff", startHoverBg: "#ebebfb" },
    dark:  { accent: "#9a97ec", accentHover: "#b0adf2", accentSoft: "#25243f", accentTextOn: "#100f1c", startHoverBg: "#25243f" },
  },
};

/* Merge an accent preset's tokens onto the base theme for the given mode. */
export function applyAccent(base, mode, accentKey) {
  const a = (ACCENTS[accentKey] || ACCENTS.graphite)[mode];
  return { ...base, ...a };
}

export const SHADOW = {
  light: {
    sm: "0 1px 2px rgba(70,80,95,.06), 0 1px 1px rgba(70,80,95,.04)",
    md: "0 4px 12px rgba(70,80,95,.08), 0 1px 3px rgba(70,80,95,.05)",
    lg: "0 12px 32px rgba(70,80,95,.12), 0 2px 8px rgba(70,80,95,.06)",
  },
  dark: {
    sm: "0 1px 2px rgba(0,0,0,.3)",
    md: "0 4px 14px rgba(0,0,0,.4)",
    lg: "0 16px 40px rgba(0,0,0,.55)",
  },
};

/* The component-facing theme object. Keys preserve the names the
   existing components already consume (appBg, sidebarBg, ...) and add
   the richer design tokens (surface2/3, verdict semantics, up/down). */
export const THEMES = {
  light: {
    // surfaces
    appBg:         "#f9fafb", // --bg
    sidebarBg:     "#ffffff", // --surface (side columns)
    cardBg:        "#ffffff", // --surface
    elevatedBg:    "#f6f7f9", // --surface-2
    surface2:      "#f6f7f9",
    surface3:      "#f0f3f5",
    // lines
    border:        "#e0e2e4", // --border
    borderStrong:  "#ced1d5", // --border-strong
    // text
    textPrimary:   "#20252a", // --text
    textSecondary: "#5d6165", // --text-2
    textMuted:     "#86898d", // --text-3
    textFaint:     "#a8abae", // --text-faint
    // accent (graphite)
    accent:        "#4f5964", // --accent
    accentHover:   "#3c4651", // --accent-hover
    accentSoft:    "#e6f0fa", // --accent-soft
    accentTextOn:  "#fcfcfd", // --accent-text-on
    startHoverBg:  "#e6f0fa",
    // verdict semantics (confirmed=green, uncertain=amber, rejected=grey)
    confirmed:     "#26894c", confirmedSoft: "#d9f8e0", confirmedBd: "#97cda5",
    uncertain:     "#cb8923", uncertainSoft: "#ffeac2", uncertainBd: "#eabb79",
    rejected:      "#7e8084", rejectedSoft:  "#edeff0", rejectedBd:  "#ced1d4",
    warning:       "#da452c", warningSoft:   "#fdeae4",
    // regulation diverging pair
    up:            "#c74c3d",
    down:          "#3676ae",
    // misc legacy keys
    dangerHoverBg: "#fbe9e4",
    codeText:      "#4f5964",
  },
  dark: {
    appBg:         "#0c0f11",
    sidebarBg:     "#15171a",
    cardBg:        "#15171a",
    elevatedBg:    "#1b1e21",
    surface2:      "#1b1e21",
    surface3:      "#212529",
    border:        "#292c30",
    borderStrong:  "#393e43",
    textPrimary:   "#e6e8ea",
    textSecondary: "#a1a5a9",
    textMuted:     "#777b7f",
    textFaint:     "#55585c",
    accent:        "#97a7b8",
    accentHover:   "#acbdce",
    accentSoft:    "#242f3b",
    accentTextOn:  "#15171a",
    startHoverBg:  "#242f3b",
    confirmed:     "#4dbf74", confirmedSoft: "#0a371b", confirmedBd: "#1e5b34",
    uncertain:     "#e8ab3e", uncertainSoft: "#4b2e01", uncertainBd: "#774f12",
    rejected:      "#83878b", rejectedSoft:  "#222427", rejectedBd:  "#3a3d41",
    warning:       "#fb784f", warningSoft:   "#3a1f17",
    up:            "#f1735c",
    down:          "#579edf",
    dangerHoverBg: "#3a1f17",
    codeText:      "#acbdce",
  },
};

/* Verdict presentation, derived from the active theme. rejected is grey
   with a minus glyph; pending is a neutral outline circle. */
export function verdictStyle(t, status) {
  switch (status) {
    case "confirmed": return { color: t.confirmed, soft: t.confirmedSoft, bd: t.confirmedBd, icon: "✓", label: "Confirmed" };
    case "uncertain": return { color: t.uncertain, soft: t.uncertainSoft, bd: t.uncertainBd, icon: "?", label: "Uncertain" };
    case "rejected":  return { color: t.rejected,  soft: t.rejectedSoft,  bd: t.rejectedBd,  icon: "–", label: "Rejected" };
    case "testing":   return { color: t.accent,    soft: t.accentSoft,    bd: t.accent,      icon: "",  label: "Testing" };
    default:          return { color: t.textMuted, soft: "transparent",   bd: t.borderStrong, icon: "○", label: "Pending" };
  }
}

/* CSS custom properties for the active theme — applied to <html> so
   class-based styling and var() references share the same palette. */
export function cssVars(mode) {
  const t = THEMES[mode];
  const s = SHADOW[mode];
  return {
    "--bg": t.appBg, "--surface": t.sidebarBg, "--surface-2": t.surface2, "--surface-3": t.surface3,
    "--border": t.border, "--border-strong": t.borderStrong,
    "--text": t.textPrimary, "--text-2": t.textSecondary, "--text-3": t.textMuted, "--text-faint": t.textFaint,
    "--accent": t.accent, "--accent-hover": t.accentHover, "--accent-soft": t.accentSoft, "--accent-text-on": t.accentTextOn,
    "--confirmed": t.confirmed, "--confirmed-soft": t.confirmedSoft, "--confirmed-bd": t.confirmedBd,
    "--uncertain": t.uncertain, "--uncertain-soft": t.uncertainSoft, "--uncertain-bd": t.uncertainBd,
    "--rejected": t.rejected, "--rejected-soft": t.rejectedSoft, "--rejected-bd": t.rejectedBd,
    "--warning": t.warning, "--warning-soft": t.warningSoft,
    "--up": t.up, "--down": t.down,
    "--r-sm": RADII.sm + "px", "--r-md": RADII.md + "px", "--r-lg": RADII.lg + "px", "--r-xl": RADII.xl + "px",
    "--shadow-sm": s.sm, "--shadow-md": s.md, "--shadow-lg": s.lg,
    "--mono": FONT_MONO, "--sans": FONT_SANS,
  };
}
