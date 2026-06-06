export default function Loading() {
  return (
    <div className="grid h-64 place-items-center" role="status" aria-label="Loading">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-neutral-300 border-t-neutral-950" />
      <span className="sr-only">Loading...</span>
    </div>
  );
}
