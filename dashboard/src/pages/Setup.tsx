import { useEffect, useState } from "react";
import { api } from "../api";

interface Props {
  onComplete: () => void;
}

export default function Setup({ onComplete }: Props) {
  const [step, setStep] = useState<"welcome" | "password" | "recovery" | "confirm" | "done">("welcome");
  const [displayName, setDisplayName] = useState("Parent");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [recovery, setRecovery] = useState<{ words: string[]; code: string } | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { setError(null); }, [step]);

  async function next() {
    setBusy(true);
    try {
      if (step === "welcome") setStep("password");
      else if (step === "password") {
        if (password.length < 10) { setError("Password must be at least 10 characters."); return; }
        if (password !== confirm) { setError("Passwords don't match."); return; }
        const rec = await api.generateRecovery();
        setRecovery(rec);
        setStep("recovery");
      } else if (step === "recovery") {
        if (!acknowledged) { setError("Please confirm you've recorded the recovery code."); return; }
        setStep("confirm");
      } else if (step === "confirm") {
        await api.setup({ display_name: displayName, password, recovery_code: recovery!.code });
        setStep("done");
        setTimeout(onComplete, 1500);
      }
    } catch (e: any) {
      setError(e.message || "Setup failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 to-white px-4 py-6">
      <div className="bg-white shadow-lg rounded-lg p-6 sm:p-8 max-w-xl w-full">
        <div className="flex items-center justify-between mb-6 gap-3">
          <div className="flex items-center gap-2">
            <img src="/icon-192.png" alt="" className="h-8 w-8" />
            <h1 className="text-2xl font-bold font-display text-brand-700">GuardianNode Setup</h1>
          </div>
          <span className="text-xs text-gray-500">step {["welcome","password","recovery","confirm","done"].indexOf(step) + 1} of 5</span>
        </div>

        {step === "welcome" && (
          <div className="space-y-4">
            <p>Welcome. Let's set up GuardianNode on this PC.</p>
            <p className="text-sm text-gray-600">
              GuardianNode runs entirely on your own hardware. It does not send your child's
              data to any cloud service. You're about to set the parent password and generate
              a recovery code that you'll need if you ever forget your password.
            </p>
            <label className="block">
              <span className="text-sm text-gray-600">Your display name (e.g. "Mom"):</span>
              <input className="border rounded w-full px-3 py-2 mt-1" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </label>
          </div>
        )}

        {step === "password" && (
          <div className="space-y-4">
            <p>Create a strong parent password. The child must <strong>not</strong> know this password.</p>
            <label className="block">
              <span className="text-sm text-gray-600">Password (min 10 characters):</span>
              <input type="password" className="border rounded w-full px-3 py-2 mt-1" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <label className="block">
              <span className="text-sm text-gray-600">Confirm password:</span>
              <input type="password" className="border rounded w-full px-3 py-2 mt-1" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
            </label>
          </div>
        )}

        {step === "recovery" && recovery && (
          <div className="space-y-4">
            <p><strong>Write down these 12 words</strong> in order. They are your recovery code.</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 my-4 bg-yellow-50 border border-yellow-200 rounded p-4 font-mono text-sm">
              {recovery.words.map((w, i) => (
                <div key={i}>
                  <span className="text-yellow-700">{i + 1}.</span> {w}
                </div>
              ))}
            </div>
            <p className="text-xs text-gray-600">
              Store this somewhere safe (filing cabinet, fireproof box, password manager). If you lose
              your password and this code, your data cannot be recovered. This is by design.
            </p>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
              <span>I've written down or saved my recovery code in a safe place.</span>
            </label>
          </div>
        )}

        {step === "confirm" && (
          <div className="space-y-4">
            <p>You're ready. Click <strong>Finish</strong> to create your admin account.</p>
            <ul className="text-sm text-gray-600 list-disc pl-5">
              <li>Parent: <strong>{displayName}</strong></li>
              <li>Password: ************</li>
              <li>Recovery code: 12 words, recorded</li>
            </ul>
          </div>
        )}

        {step === "done" && (
          <div className="text-green-700 text-center py-8">
            <div className="text-4xl mb-2">✓</div>
            <div>Setup complete. Opening dashboard…</div>
          </div>
        )}

        {error && <div className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">{error}</div>}

        {step !== "done" && (
          <div className="mt-6 flex justify-end gap-2">
            <button
              onClick={next}
              disabled={busy}
              className="bg-brand-500 hover:bg-brand-700 text-white px-4 py-2 rounded disabled:opacity-50"
            >
              {step === "confirm" ? "Finish" : "Next"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
