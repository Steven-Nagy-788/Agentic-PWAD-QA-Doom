import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 p-6">
      <h2 className="text-xl font-semibold text-neutral-900">Page not found</h2>
      <p className="text-sm text-neutral-500">
        The page you are looking for does not exist.
      </p>
      <Link
        href="/"
        className="mt-2 rounded bg-neutral-950 px-4 py-2 text-sm font-semibold text-white hover:bg-neutral-800"
      >
        Back to dashboard
      </Link>
    </div>
  );
}
