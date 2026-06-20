import { useState } from "react";
import { api } from "../api";

interface Props {
  onLogin: (user: { display_name: string; role: string }) => void;
}

export default function Login({ onLogin }: Props) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showRecovery, setShowRecovery] = useState(false);
  const [recoveryCode, setRecoveryCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const u = await api.login(password);
      onLogin(u);
    } catch (e: any) {
      setError("Sign-in failed. Check your password.");
    } finally { setBusy(false); }
  }

  async function recover(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api.recoveryReset(recoveryCode, newPassword);
      const u = await api.login(newPassword);
      onLogin(u);
    } catch (e: any) {
      setError("Recovery failed. Check your recovery code.");
    } finally { setBusy(false); }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 to-white px-4">
      <div className="bg-white shadow-lg rounded-lg p-6 sm:p-8 w-full max-w-md">
        <img src="/logo-vertical.png" alt="GuardianNode — Protecting Families, Privately." className="mx-auto mb-4 w-48" />
        <h1 className="sr-only">GuardianNode</h1>
        <p className="text-sm text-gray-500 mb-6 text-center">Sign in to review alerts.</p>
        {!showRecovery ? (
          <form onSubmit={submit} className="space-y-3">
            <input type="password" placeholder="Parent password"
                   className="w-full border rounded px-3 py-2"
                   value={password} onChange={(e) => setPassword(e.target.value)} />
            {error && <div className="text-sm text-red-700">{error}</div>}
            <button type="submit" disabled={busy}
                    className="w-full bg-brand-500 hover:bg-brand-700 text-white py-2 rounded">
              Sign in
            </button>
            <button type="button" onClick={() => setShowRecovery(true)}
                    className="block mx-auto text-sm text-brand-700 underline">
              Forgot password? Use recovery code
            </button>
          </form>
        ) : (
          <form onSubmit={recover} className="space-y-3">
            <textarea placeholder="12-word recovery code"
                      className="w-full border rounded px-3 py-2 h-24 font-mono text-sm"
                      value={recoveryCode} onChange={(e) => setRecoveryCode(e.target.value)} />
            <input type="password" placeholder="New password (min 10 chars)"
                   className="w-full border rounded px-3 py-2"
                   value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            {error && <div className="text-sm text-red-700">{error}</div>}
            <button type="submit" disabled={busy}
                    className="w-full bg-brand-500 hover:bg-brand-700 text-white py-2 rounded">
              Reset password
            </button>
            <button type="button" onClick={() => setShowRecovery(false)}
                    className="block mx-auto text-sm text-gray-500 underline">
              Back to sign-in
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
