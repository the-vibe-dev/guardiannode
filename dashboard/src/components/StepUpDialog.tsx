import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { registerStepUpHandler } from "../stepUp";

type Challenge = {
  level: string;
  resolve: () => void;
  reject: (reason: Error) => void;
};

export default function StepUpDialog() {
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => registerStepUpHandler((level) => new Promise<void>((resolve, reject) => {
    setPassword("");
    setError("");
    setChallenge({ level, resolve, reject });
  })), []);

  useEffect(() => {
    if (challenge) dialogRef.current?.showModal();
    else dialogRef.current?.close();
  }, [challenge]);

  function cancel() {
    if (busy || !challenge) return;
    challenge.reject(new Error("Password confirmation cancelled."));
    setPassword("");
    setChallenge(null);
  }

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    if (!challenge || busy) return;
    setBusy(true);
    setError("");
    try {
      await api.reauth(password);
      challenge.resolve();
      setPassword("");
      setChallenge(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not confirm your password. Try again.");
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog ref={dialogRef} aria-labelledby="step-up-title" aria-describedby="step-up-description"
      onCancel={(event) => { event.preventDefault(); cancel(); }}
      className="step-up-dialog fixed left-1/2 top-1/2 w-[calc(100%-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-gray-200 bg-white p-6 text-gray-900 shadow-xl backdrop:bg-gray-950/50">
      {challenge && <form onSubmit={confirm} className="flex min-w-72 max-w-sm flex-col gap-4">
        <h2 id="step-up-title" className="text-lg font-semibold">Confirm your password</h2>
        <p id="step-up-description" className="text-sm text-gray-600">
          {challenge.level === "critical" ? "Confirm this security action." : "Confirm this action."}
        </p>
        <label htmlFor="step-up-password" className="text-sm font-medium">Parent password</label>
        <input id="step-up-password" type="password" autoComplete="current-password" autoFocus
          required value={password} onChange={(event) => setPassword(event.target.value)}
          className="rounded-md border border-gray-300 px-3 py-2" />
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <div className="flex justify-end gap-3">
          <button type="button" onClick={cancel} disabled={busy} className="rounded-md px-3 py-2">Cancel</button>
          <button type="submit" disabled={busy} className="rounded-md bg-blue-700 px-3 py-2 text-white disabled:opacity-60">
            {busy ? "Confirming…" : "Continue"}
          </button>
        </div>
      </form>}
    </dialog>
  );
}
