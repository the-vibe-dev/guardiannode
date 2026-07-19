import { NavLink } from "react-router-dom";
import { ReactNode } from "react";

interface Props {
  children: ReactNode;
  user: { display_name: string; role: string };
  onLogout: () => void;
}

const nav = [
  { to: "/", label: "Overview" },
  { to: "/risks", label: "Risk feed" },
  { to: "/devices", label: "Devices" },
  { to: "/profiles", label: "Profiles" },
  { to: "/models", label: "Models" },
  { to: "/settings", label: "Settings" },
  { to: "/audit", label: "Audit" },
  { to: "/guardian-reviews", label: "Review history" },
  { to: "/demo", label: "Demo" },
];

export default function Layout({ children, user, onLogout }: Props) {
  return (
    <div className="min-h-screen md:flex">
      <aside className="bg-brand-700 text-white flex flex-col md:w-56 md:min-h-screen">
        <div className="p-4 border-b border-brand-500/40 flex items-start justify-between gap-3 md:block">
          <div>
          <div className="flex items-center gap-2">
            <img src="/icon-192.png" alt="" className="h-6 w-6" />
            <span className="font-display font-bold text-lg">GuardianNode</span>
          </div>
          <div className="text-xs text-brand-100">local-first family safety</div>
          </div>
          <button
            onClick={onLogout}
            className="text-xs px-2 py-1 rounded bg-white/10 hover:bg-white/20 md:hidden"
          >
            Sign out
          </button>
        </div>
        <nav className="flex gap-1 overflow-x-auto p-3 md:block md:flex-1 md:space-y-1">
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                "block shrink-0 px-3 py-2 rounded text-sm " +
                (isActive ? "bg-white/15 font-semibold" : "hover:bg-white/10")
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden p-3 border-t border-brand-500/40 text-sm md:block">
          <div className="font-medium">{user.display_name}</div>
          <div className="text-xs text-brand-100">{user.role}</div>
          <div className="mt-3 text-xs text-brand-100">
            <div>v0.1.0-alpha.2</div>
            <a className="underline" href="https://github.com/the-vibe-dev/guardiannode" rel="noreferrer">
              AGPL-3.0 source
            </a>
            <div>No warranty.</div>
          </div>
          <button
            onClick={onLogout}
            className="mt-2 text-xs px-2 py-1 rounded bg-white/10 hover:bg-white/20"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto bg-gray-50 p-4 md:p-6">
        {children}
      </main>
    </div>
  );
}
