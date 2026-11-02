import { MoreHorizontal, Plus, Send, Sparkles, Trash2, AlertCircle } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { conversationService } from "../services/conversations";
import type { Conversation } from "../types/conversations";
import { MarkdownRenderer } from "../components/markdown-renderer";

export function ChatPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [investigationError, setInvestigationError] = useState<string | null>(null);
  const conversations = useQuery({ queryKey: ["conversations"], queryFn: conversationService.list });
  const messages = useQuery({ queryKey: ["messages", selectedId], queryFn: () => conversationService.messages(selectedId!), enabled: Boolean(selectedId) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["conversations"] });
  const create = useMutation({ mutationFn: () => conversationService.create("New investigation"), onSuccess: (conversation) => { setSelectedId(conversation.id); refresh(); } });
  const remove = useMutation({ mutationFn: conversationService.remove, onSuccess: (_, id) => { if (id === selectedId) setSelectedId(null); refresh(); } });
  
  const investigate = useMutation({ 
    mutationFn: ({ id, content }: { id: string; content: string }) => conversationService.investigate(id, content), 
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["messages", selectedId] });
      setInvestigationError(null);
    },
    onError: (error: Error) => {
      setInvestigationError(error.message || "Investigation failed. Please try again.");
      queryClient.invalidateQueries({ queryKey: ["messages", selectedId] });
    }
  });

  useEffect(() => { const requested = searchParams.get("conversation"); if (!selectedId && requested && conversations.data?.items.some((item) => item.id === requested)) setSelectedId(requested); else if (!selectedId && conversations.data?.items[0]) setSelectedId(conversations.data.items[0].id); }, [conversations.data, selectedId, searchParams]);
  
  async function submit(event: FormEvent<HTMLFormElement>) { 
    event.preventDefault(); 
    if (!selectedId || !draft.trim() || investigate.isPending) return;
    const question = draft;
    setDraft("");
    setInvestigationError(null);
    try {
      await investigate.mutateAsync({ id: selectedId, content: question });
    } catch (error) {
      // Error handled by mutation onError
      console.error("Investigation error:", error);
    }
  }

  return <section className="mx-auto grid h-[calc(100vh-5rem)] max-w-6xl overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/30 md:grid-cols-[17rem_1fr]"><aside className="border-b border-zinc-800 p-3 md:border-b-0 md:border-r"><button className="flex w-full items-center justify-center gap-2 rounded-md bg-cyan-400 px-3 py-2 text-sm font-medium text-zinc-950" onClick={() => create.mutate()}><Plus size={16} />New conversation</button><div className="mt-3 space-y-1">{conversations.data?.items.map((conversation) => <ConversationItem conversation={conversation} active={conversation.id === selectedId} key={conversation.id} onDelete={() => remove.mutate(conversation.id)} onSelect={() => setSelectedId(conversation.id)} />)}{!conversations.data?.items.length && !conversations.isLoading && <p className="p-3 text-sm text-zinc-500">No conversations yet.</p>}</div></aside><div className="flex min-h-0 flex-col"><header className="border-b border-zinc-800 px-6 py-4"><h1 className="font-semibold">AI Chat</h1><p className="mt-1 text-sm text-zinc-500">Ask infrastructure questions using cloud AI with Prometheus and Qdrant context.</p></header><div className="flex-1 overflow-y-auto p-6">{selectedId ? <>{investigationError && <div className="mb-4 rounded-lg border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-200"><AlertCircle className="mr-2 inline" size={16} />{investigationError}</div>}{messages.data?.items.map((message) => <article className="mb-4 rounded-lg border border-zinc-800 bg-zinc-950/60 p-4" key={message.id}><p className="mb-2 text-xs font-medium uppercase tracking-wide text-cyan-300">{message.role}</p>{message.role === "assistant" ? <MarkdownRenderer content={message.content} /> : <p className="whitespace-pre-wrap text-sm leading-6 text-zinc-200">{message.content}</p>}</article>)}{investigate.isPending && <div className="mb-4 rounded-lg border border-cyan-400/20 bg-cyan-400/5 p-4 text-sm text-cyan-200"><Sparkles className="mr-2 inline animate-pulse" size={16} />Investigating with cloud AI router...</div>}</> : <div className="grid h-full place-items-center text-center text-zinc-500"><div><Sparkles className="mx-auto mb-3" /><p>Create or select a conversation to start an AI investigation.</p></div></div>}</div><form className="border-t border-zinc-800 p-4" onSubmit={submit}><div className="flex gap-3"><textarea className="min-h-12 flex-1 resize-none rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm outline-none focus:border-cyan-400 disabled:opacity-50" disabled={!selectedId || investigate.isPending} placeholder={selectedId ? "Ask an infrastructure question…" : "Select a conversation first"} value={draft} onChange={(event) => setDraft(event.target.value)} /><button aria-label="Send message" className="rounded-md bg-cyan-400 px-3 text-zinc-950 disabled:opacity-50" disabled={!selectedId || !draft.trim() || investigate.isPending}><Send size={18} /></button></div></form></div></section>;
}

function ConversationItem({ conversation, active, onDelete, onSelect }: { conversation: Conversation; active: boolean; onDelete: () => void; onSelect: () => void }) { return <div className={`group flex items-center rounded-md ${active ? "bg-zinc-800" : "hover:bg-zinc-900"}`}><button className="min-w-0 flex-1 truncate px-3 py-2 text-left text-sm text-zinc-300" onClick={onSelect}>{conversation.title}</button><button aria-label={`Delete ${conversation.title}`} className="p-2 text-zinc-500 opacity-0 group-hover:opacity-100 hover:text-red-300" onClick={onDelete}><Trash2 size={14} /></button><MoreHorizontal className="hidden" /></div>; }
