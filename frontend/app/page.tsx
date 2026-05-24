"use client";

/* eslint-disable @next/next/no-img-element */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type React from "react";
import { useRouter } from "next/navigation";
import { Upload } from "lucide-react";
import { WadFile, WadMap, apiGet, assetUrl, uploadWad } from "@/lib/api";
import { Metric, SkeletonRows, InlineError, errorMessage, formatBytes } from "@/lib/components/shared";

export default function WadLibraryPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const wads = useQuery({ queryKey: ["wads"], queryFn: () => apiGet<WadFile[]>("/wads") });
  const uploadMutation = useMutation({
    mutationFn: uploadWad,
    onSuccess: (wad) => {
      queryClient.invalidateQueries({ queryKey: ["wads"] });
      router.push(`/wad/${wad.id}`);
    },
  });

  return (
    <div className="space-y-5 p-4 lg:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">WAD Library</h2>
          <p className="text-sm text-neutral-500">{(wads.data ?? []).length} files</p>
        </div>
        <UploadZone busy={uploadMutation.isPending} onUpload={(file) => uploadMutation.mutate(file)} />
      </div>
      {uploadMutation.error ? <InlineError message={errorMessage(uploadMutation.error) ?? "Upload failed"} /> : null}
      {wads.error ? <InlineError message={errorMessage(wads.error) ?? "Failed to load WADs"} /> : null}
      {wads.isLoading ? <SkeletonRows /> : null}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {(wads.data ?? []).map((wad) => (
          <button key={wad.id} onClick={() => router.push(`/wad/${wad.id}`)} className="overflow-hidden rounded border border-neutral-200 bg-white text-left shadow-sm transition hover:border-neutral-400">
            <WadThumbnail wadId={wad.id} />
            <div className="space-y-3 p-4">
              <div>
                <h3 className="truncate text-sm font-semibold">{wad.original_filename}</h3>
                <p className="text-xs text-neutral-500">{formatBytes(wad.file_size_bytes)} · {wad.iwad_required}</p>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Metric label="Maps" value={wad.detected_maps?.length ?? 0} />
                <Metric label="Uploaded" value={new Date(wad.uploaded_at).toLocaleDateString()} />
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function WadThumbnail({ wadId }: { wadId: string }) {
  const maps = useQuery({ queryKey: ["wad-thumb", wadId], queryFn: () => apiGet<WadMap[]>(`/wads/${wadId}/maps`) });
  const first = maps.data?.[0];
  return (
    <div className="aspect-[16/9] bg-neutral-950">
      {first?.map_overview_png_url ? <img src={assetUrl(first.map_overview_png_url)} alt={first.map_name} className="h-full w-full object-cover" /> : null}
    </div>
  );
}

function UploadZone({ busy, onUpload }: { busy: boolean; onUpload: (file: File) => void }) {
  const pick = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) onUpload(file);
  };
  const drop = (event: React.DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) onUpload(file);
  };
  return (
    <>
      <span id="upload-description" className="sr-only">Upload a WAD file to analyze it for map defects</span>
      <label
        onDragOver={(event) => event.preventDefault()}
        onDrop={drop}
        className="inline-flex h-11 cursor-pointer items-center gap-2 rounded border border-neutral-300 bg-white px-4 text-sm font-semibold hover:border-neutral-500"
        aria-label="Upload WAD file"
        aria-describedby="upload-description"
      >
        <Upload className="h-4 w-4" aria-hidden="true" />
        {busy ? "Uploading" : "Upload"}
        <input className="sr-only" type="file" accept=".wad" onChange={pick} />
      </label>
    </>
  );
}
