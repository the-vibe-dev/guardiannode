import { NavLink } from "react-router-dom";
import { ReactNode, useState } from "react";
import {
  Bell, Bot, ClipboardList, Cpu, FileClock, HeartHandshake, Home, Laptop, LogOut,
  Menu, ShieldCheck, UserRound, UsersRound, X,
} from "lucide-react";

interface Props {
  children: ReactNode;
  user: { display_name: string; role: string };
  onLogout: () => void;
}

const coreNav = [
  { to: "/", label: "Home", icon: Home },
  { to: "/risks", label: "Alerts", icon: Bell },
  { to: "/profiles", label: "Children", icon: UsersRound },
  { to: "/devices", label: "Devices", icon: Laptop },
  { to: "/requests", label: "Requests", icon: ClipboardList },
];

const advancedNav = [
  { to: "/privacy", label: "Privacy & consent", icon: HeartHandshake },
  { to: "/models", label: "Models", icon: Bot },
  { to: "/audit", label: "Audit", icon: FileClock },
  { to: "/guardian-reviews", label: "Review history", icon: ShieldCheck },
  { to: "/settings", label: "Diagnostics & settings", icon: Cpu },
];

export default function Layout({ children, user, onLogout }: Props) {
  const [open, setOpen] = useState(false);
  const navLink = (item: typeof coreNav[number]) => {
    const Icon = item.icon;
    return (
      <NavLink
        key={item.to}
        to={item.to}
        end={item.to === "/"}
        onClick={() => setOpen(false)}
        className={({ isActive }) =>
          `flex min-h-11 items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
            isActive ? "bg-white/15 font-semibold text-white" : "text-teal-50 hover:bg-white/10 hover:text-white"
          }`
        }
      >
        <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
        {item.label}
      </NavLink>
    );
  };

  return (
    <div className="min-h-screen bg-[#f3f6f8] md:flex">
      <header className="sticky top-0 z-40 flex h-16 items-center justify-between bg-[#0d3b4a] px-4 text-white md:hidden">
        <Brand />
        <button className="flex min-h-11 items-center gap-2 rounded-lg border border-white/30 px-3 py-2 text-sm font-semibold hover:bg-white/10" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="mobile-navigation" aria-label={open ? "Close navigation" : "Open navigation"}>
          {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          <span>{open ? "Close" : "Menu"}</span>
        </button>
      </header>
      {open && <button className="fixed inset-0 z-30 bg-slate-950/30 md:hidden" onClick={() => setOpen(false)} aria-label="Close navigation overlay" />}
      <aside id="mobile-navigation" className={`${open ? "translate-x-0" : "-translate-x-full"} fixed inset-y-0 left-0 z-40 flex w-[min(84vw,280px)] flex-col bg-[#0d3b4a] p-4 text-white transition-transform md:sticky md:top-0 md:h-screen md:w-[248px] md:translate-x-0`}>
        <div className="hidden px-2 pb-7 pt-2 md:block"><Brand /></div>
        <nav aria-label="Primary" className="space-y-1">{coreNav.map(navLink)}</nav>
        <div className="my-5 border-t border-white/15" />
        <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-[0.16em] text-teal-100">Advanced</p>
        <nav aria-label="Advanced" className="space-y-1">{advancedNav.map(navLink)}</nav>
        <div className="mt-auto border-t border-white/15 pt-4">
          <NavLink to="/settings" onClick={() => setOpen(false)} className="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-teal-50 hover:bg-white/10">
            <UserRound aria-hidden="true" size={18} />
            <span><span className="block font-medium text-white">{user.display_name}</span><span className="block text-xs capitalize text-teal-100">{user.role}</span></span>
          </NavLink>
          <button onClick={onLogout} className="mt-1 flex min-h-11 w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-teal-50 hover:bg-white/10 hover:text-white">
            <LogOut aria-hidden="true" size={18} /> Sign out
          </button>
          <div className="px-3 pt-3 text-[10px] text-teal-100">GuardianNode v0.1.0-alpha.3 · Local-first</div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto px-4 py-6 sm:px-6 md:px-8 md:py-8">
        <div className="mx-auto w-full max-w-[1280px]">{children}</div>
      </main>
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid h-9 w-9 place-items-center rounded-lg bg-white/10"><ShieldCheck aria-hidden="true" size={22} /></span>
      <span><span className="block font-display text-base font-bold tracking-tight">GuardianNode</span><span className="block text-[10px] tracking-wide text-teal-100">Family safety, at home</span></span>
    </div>
  );
}
