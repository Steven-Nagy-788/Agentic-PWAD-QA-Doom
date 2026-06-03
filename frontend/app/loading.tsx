export default function Loading() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-neutral-200 border-t-neutral-950" />
        <p className="text-sm text-neutral-500">Loading...</p>
      </div>
    </div>
  );
}
