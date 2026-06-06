"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-6" role="alert">
      <h2 className="text-xl font-semibold text-neutral-900">Something went wrong</h2>
      <p className="text-sm text-neutral-500 max-w-md text-center">
        {error.message || "An unexpected error occurred."}
      </p>
      {error.digest && (
        <p className="text-xs text-neutral-400 font-mono">Error: {error.digest}</p>
      )}
      <button
        onClick={reset}
        className="mt-2 rounded bg-neutral-950 px-4 py-2 text-sm font-semibold text-white hover:bg-neutral-800"
      >
        Try again
      </button>
    </div>
  );
}
