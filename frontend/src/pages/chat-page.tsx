import { AlertCircle, MoreHorizontal, Plus, Send, Sparkles, Trash2 } from "lucide-react";
import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { conversationService } from "../services/conversations";
import type { Conversation } from "../types/conversations";
import { MarkdownRenderer } from "../components/markdown-renderer";

export function ChatPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get("conversation"));
  const [draft, setDraft] = useState("");
  const [investigationError, setInvestigationError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const composer = useRef<HTMLTextAreaElement>(null);
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: conversationService.list });
  const messages = useQuery({
    queryKey: ["messages", selectedId],
    queryFn: () => conversationService.messages(selectedId!),
    enabled: Boolean(selectedId),
  });

  useEffect(() => {
    const requested = searchParams.get("conversation");
    if (requested && conversations.data?.items.some((item) => item.id === requested)) {
      setSelectedId(requested);
      return;
    }
    if (!selectedId && conversations.data?.items[0]) selectConversation(conversations.data.items[0].id);
  }, [conversations.data, searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  function selectConversation(id: string) {
    setSelectedId(id);
    setSearchParams({ conversation: id });
    setInvestigationError(null);
  }

  const create = useMutation({
    mutationFn: () => conversationService.create("New investigation"),
    onSuccess: (conversation) => {
      queryClient.setQueryData<{ items: Conversation[] }>(["conversations"], (current) => ({
        items: [conversation, ...(current?.items ?? [])],
      }));
      selectConversation(conversation.id);
      composer.current?.focus();
    },
  });

  const remove = useMutation({
    mutationFn: conversationService.remove,
    onSuccess: (_, id) => {
      if (id === selectedId) {
        const next = conversations.data?.items.find((item) => item.id !== id);
        if (next) selectConversation(next.id);
        else {
          setSelectedId(null);
          setSearchParams({});
        }
      }
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const investigate = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) => conversationService.investigate(id, content),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["messages", variables.id] });
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
      setInvestigationError(null);
    },
    onError: (error: Error) => setInvestigationError(error.message || "Investigation failed. Try again."),
  });

  async function ensureConversation(): Promise<string> {
    if (selectedId) return selectedId;
    setCreating(true);
    try {
      const conversation = await create.mutateAsync();
      return conversation.id;
    } finally {
      setCreating(false);
    }
  }

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    const question = draft.trim();
    if (!question || investigate.isPending || creating) return;
    setInvestigationError(null);
    try {
      const id = await ensureConversation();
      await investigate.mutateAsync({ id, content: question });
      setDraft("");
    } catch (error) {
      setInvestigationError(error instanceof Error ? error.message : "Investigation failed. Your message is still in the composer.");
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  const hasConversation = Boolean(selectedId);
  return <section className="mx-auto grid h-[calc(100vh-5rem)] max-w-6xl overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/30 md:grid-cols-[17rem_1fr]">
    <aside className="border-b border-zinc-800 p-3 md:border-b-0 md:border-r">
      <button className="flex w-full items-center justify-center gap-2 rounded-md bg-cyan-400 px-3 py-2 text-sm font-medium text-zinc-950 disabled:opacity-60" onClick={() => create.mutate()} disabled={create.isPending}><Plus size={16} />{create.isPending ? "Creating…" : "New conversation"}</button>
      <div className="mt-3 space-y-1">{conversations.data?.items.map((conversation) => <ConversationItem conversation={conversation} active={conversation.id === selectedId} key={conversation.id} onDelete={() => remove.mutate(conversation.id)} onSelect={() => selectConversation(conversation.id)} />)}{!conversations.data?.items.length && !conversations.isLoading && <p className="p-3 text-sm text-zinc-500">No conversations yet. Send a message to start one.</p>}</div>
    </aside>
    <div className="flex min-h-0 flex-col">
      <header className="border-b border-zinc-800 px-6 py-4"><h1 className="font-semibold">AI Chat</h1><p className="mt-1 text-sm text-zinc-500">Evidence-based investigations using the LangGraph workflow, Prometheus, Docker and Qdrant.</p></header>
      <div className="flex-1 overflow-y-auto p-6">
        {!hasConversation && <div className="grid h-full place-items-center text-center"><div><Sparkles className="mx-auto text-cyan-300" size={28} /><h2 className="mt-3 font-medium">Start an infrastructure investigation</h2><p className="mt-2 max-w-md text-sm text-zinc-500">Type a question below. KiboLens will create and persist the conversation automatically, or use New conversation to name it first.</p></div></div>}
        {hasConversation && <>{messages.isLoading && <p className="text-sm text-zinc-500">Loading conversation history…</p>}{investigationError && <div className="mb-4 rounded-lg border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-200"><AlertCircle className="mr-2 inline" size={16} />{investigationError}</div>}{messages.data?.items.map((message) => <article className="mb-4 rounded-lg border border-zinc-800 bg-zinc-950/60 p-4" key={message.id}><p className="mb-2 text-xs font-medium uppercase tracking-wide text-cyan-300">{message.role}</p>{message.role === "assistant" ? <MarkdownRenderer content={message.content} /> : <p className="whitespace-pre-wrap text-sm leading-6 text-zinc-200">{message.content}</p>}</article>)}{investigate.isPending && <div className="mb-4 rounded-lg border border-cyan-400/20 bg-cyan-400/5 p-4 text-sm text-cyan-200"><Sparkles className="mr-2 inline animate-pulse" size={16} />Collecting evidence and investigating…</div>}</>}
      </div>
      <form className="border-t border-zinc-800 p-4" onSubmit={(event) => void submit(event)}><div className="flex items-end gap-3"><textarea ref={composer} aria-label="Investigation question" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="Ask why a service failed, how CPU changed, or what this incident means…" rows={2} disabled={investigate.isPending || creating} className="min-h-12 flex-1 resize-none rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm outline-none focus:border-cyan-400 disabled:opacity-60" /><button aria-label="Send investigation" className="rounded-md bg-cyan-400 p-3 text-zinc-950 disabled:opacity-50" disabled={!draft.trim() || investigate.isPending || creating}><Send size={17} /></button></div><p className="mt-2 text-xs text-zinc-600">Enter to send · Shift+Enter for a new line · messages are retained in the selected conversation.</p></form>
    </div>
  </section>;
}

function ConversationItem({ conversation, active, onDelete, onSelect }: { conversation: Conversation; active: boolean; onDelete: () => void; onSelect: () => void }) { return <div className={`group flex items-center rounded-md ${active ? "bg-zinc-800" : "hover:bg-zinc-900"}`}><button className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm text-zinc-300" onClick={onSelect}>{conversation.title}</button><button aria-label={`Delete ${conversation.title}`} className="p-2 text-zinc-500 opacity-0 group-hover:opacity-100 hover:text-red-300" onClick={onDelete}><Trash2 size={14} /></button><MoreHorizontal className="hidden" /></div>; }
