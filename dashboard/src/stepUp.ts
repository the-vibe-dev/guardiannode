type StepUpHandler = (level: string) => Promise<void>;

let handler: StepUpHandler | null = null;
let pending: Promise<void> | null = null;

export function registerStepUpHandler(next: StepUpHandler): () => void {
  handler = next;
  return () => {
    if (handler === next) handler = null;
  };
}

export function requestStepUp(level: string): Promise<void> {
  if (pending) return pending;
  if (!handler) return Promise.reject(new Error("Sign in again to continue."));
  pending = handler(level).finally(() => { pending = null; });
  return pending;
}
