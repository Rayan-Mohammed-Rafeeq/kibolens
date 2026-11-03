import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Search, Upload, Trash2 } from "lucide-react";
import { useState } from "react";
import { documentsService } from "../services/documents";
import { ConfirmDialog } from "../components/dialog";

export function KnowledgeBasePage() {
  const client = useQueryClient();
  const [query, setQuery] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [pendingDelete, setPendingDelete] = useState<{ id: string; filename: string } | null>(null);
  const documents = useQuery({ queryKey: ["documents"], queryFn: documentsService.list });
  const search = useQuery({ queryKey: ["document-search", searchTerm], queryFn: () => documentsService.search(searchTerm), enabled: searchTerm.length > 0 });
  const upload = useMutation({ mutationFn: documentsService.upload, onSuccess: () => client.invalidateQueries({ queryKey: ["documents"] }) });
  const remove = useMutation({ mutationFn: documentsService.remove, onSuccess: () => client.invalidateQueries({ queryKey: ["documents"] }) });

  return <section className="mx-auto max-w-6xl">
    <p className="text-sm font-medium text-cyan-300">Evidence and runbooks</p>
    <h1 className="mt-2 text-3xl font-semibold tracking-tight">Knowledge Base</h1>
    <p className="mt-2 text-zinc-400">Upload documentation that the AI investigator can retrieve. Secrets are redacted before indexing.</p>
    <div className="mt-6 grid gap-4 lg:grid-cols-[1fr_1fr]">
      <form className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5" onSubmit={(event) => { event.preventDefault(); if (query) setSearchTerm(query); }}>
        <h2 className="font-medium">Search indexed documents</h2>
        <div className="mt-3 flex gap-2"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search runbooks, logs, configuration…" className="min-w-0 flex-1 rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm" /><button className="rounded-md bg-cyan-400 px-3 text-zinc-950" aria-label="Search"><Search size={16} /></button></div>
        {search.isError && <p className="mt-3 text-sm text-red-300">{(search.error as Error).message}</p>}
        <div className="mt-4 space-y-3">{search.data?.results.map((result) => <article key={`${result.document_id}-${result.chunk_index}`} className="rounded-md border border-zinc-800 p-3"><div className="flex justify-between gap-3 text-xs text-zinc-500"><span>{result.filename}</span><span>score {result.score.toFixed(3)}</span></div><p className="mt-2 whitespace-pre-wrap text-sm text-zinc-300">{result.text}</p></article>)}{search.data && search.data.results.length === 0 && <p className="text-sm text-zinc-500">No indexed matches.</p>}</div>
      </form>
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5"><h2 className="font-medium">Ingest document</h2><label className="mt-4 flex cursor-pointer items-center justify-center gap-2 rounded-md border border-dashed border-zinc-700 p-6 text-sm text-zinc-400 hover:border-cyan-400/60 hover:text-cyan-300"><Upload size={17} />Choose PDF, DOCX, Markdown, YAML, Dockerfile or log<input type="file" className="hidden" accept=".pdf,.docx,.txt,.md,.markdown,.yaml,.yml,.log,.dockerfile,.conf" onChange={(event) => { const file = event.target.files?.[0]; if (file) upload.mutate(file); }} /></label>{upload.isPending && <p className="mt-3 text-sm text-cyan-300">Extracting, chunking and indexing…</p>}{upload.isError && <p className="mt-3 text-sm text-red-300">{(upload.error as Error).message}</p>}{upload.data && <p className="mt-3 text-sm text-emerald-300">Indexed {upload.data.filename} ({upload.data.chunks} chunks).</p>}</div>
    </div>
     <div className="mt-6 rounded-xl border border-zinc-800 bg-zinc-900/40"><header className="border-b border-zinc-800 px-5 py-4"><h2 className="font-medium">Indexed documents</h2></header>{documents.isLoading ? <p className="p-5 text-sm text-zinc-500">Loading documents…</p> : documents.data?.length ? <div className="divide-y divide-zinc-800">{documents.data.map((document) => <div className="flex items-center justify-between gap-4 p-4" key={document.document_id}><div className="flex min-w-0 items-center gap-3"><FileText size={17} className="text-cyan-300" /><div className="min-w-0"><p className="truncate text-sm text-zinc-200">{document.filename}</p><p className="text-xs text-zinc-500">{document.total_chunks} chunks · indexed {new Date(document.uploaded_at).toLocaleString()}</p></div></div><button className="text-zinc-500 transition hover:text-red-300" aria-label={`Delete ${document.filename}`} onClick={() => setPendingDelete({ id: document.document_id, filename: document.filename })}><Trash2 size={16} /></button></div>)}</div> : <p className="p-5 text-sm text-zinc-500">No documents have been indexed yet.</p>}</div>
     <ConfirmDialog open={Boolean(pendingDelete)} title="Delete knowledge base document?" description={`“${pendingDelete?.filename ?? "This document"}” and its indexed chunks will be permanently removed.`} confirmLabel="Delete" destructive busy={remove.isPending} onCancel={() => setPendingDelete(null)} onConfirm={() => { if (pendingDelete) remove.mutate(pendingDelete.id, { onSuccess: () => setPendingDelete(null) }); }} />
  </section>;
}
