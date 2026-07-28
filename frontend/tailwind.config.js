/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          navy: "#0b1220",
          panel: "#111827",
          teal: "#0f766e",
          tealDark: "#115e59",
          tealSoft: "#ccfbf1"
        },
        surface: {
          app: "#f5f7fb",
          base: "#ffffff",
          muted: "#f8fafc",
          raised: "#ffffff"
        },
        text: {
          primary: "#111827",
          secondary: "#64748b",
          muted: "#94a3b8",
          inverse: "#f8fafc"
        },
        border: {
          subtle: "#e2e8f0",
          strong: "#cbd5e1"
        },
        semantic: {
          success: "#047857",
          successBg: "#ecfdf5",
          warning: "#b45309",
          warningBg: "#fffbeb",
          danger: "#be123c",
          dangerBg: "#fff1f2",
          info: "#1d4ed8",
          infoBg: "#eff6ff"
        },
        ink: "#111827",
        slatepanel: "#111827",
        mist: "#f5f7fb",
        line: "#e2e8f0",
        teal: "#0f766e",
        amber: "#b45309",
        rose: "#be123c"
      },
      boxShadow: {
        panel: "0 1px 2px rgba(15, 23, 42, 0.08)",
        floating: "0 16px 40px rgba(15, 23, 42, 0.16)"
      },
      borderRadius: {
        control: "0.5rem",
        panel: "0.75rem"
      },
      spacing: {
        sidebar: "19rem"
      }
    }
  },
  plugins: []
};
