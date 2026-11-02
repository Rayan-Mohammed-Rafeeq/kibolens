import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  const components: Components = {
    // Headings
    h1: ({ children }) => (
      <h1 className="mb-4 mt-6 text-2xl font-bold text-zinc-100 first:mt-0">
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className="mb-3 mt-5 text-xl font-bold text-zinc-100 first:mt-0">
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="mb-3 mt-4 text-lg font-semibold text-zinc-100 first:mt-0">
        {children}
      </h3>
    ),
    h4: ({ children }) => (
      <h4 className="mb-2 mt-4 text-base font-semibold text-zinc-200 first:mt-0">
        {children}
      </h4>
    ),
    h5: ({ children }) => (
      <h5 className="mb-2 mt-3 text-sm font-semibold text-zinc-200 first:mt-0">
        {children}
      </h5>
    ),
    h6: ({ children }) => (
      <h6 className="mb-2 mt-3 text-sm font-medium text-zinc-300 first:mt-0">
        {children}
      </h6>
    ),

    // Paragraphs
    p: ({ children }) => (
      <p className="mb-4 leading-7 text-zinc-200 last:mb-0">{children}</p>
    ),

    // Lists
    ul: ({ children }) => (
      <ul className="mb-4 ml-6 list-disc space-y-2 text-zinc-200 last:mb-0">
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className="mb-4 ml-6 list-decimal space-y-2 text-zinc-200 last:mb-0">
        {children}
      </ol>
    ),
    li: ({ children }) => <li className="leading-7">{children}</li>,

    // Emphasis
    strong: ({ children }) => (
      <strong className="font-semibold text-zinc-100">{children}</strong>
    ),
    em: ({ children }) => <em className="italic text-zinc-200">{children}</em>,

    // Code
    code: (props) => {
      const { inline, children } = props as { inline?: boolean; children: React.ReactNode };
      return inline ? (
        <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-sm text-cyan-300">
          {children}
        </code>
      ) : (
        <code className="block rounded-lg bg-zinc-900 p-4 font-mono text-sm text-zinc-200 overflow-x-auto">
          {children}
        </code>
      );
    },
    pre: ({ children }) => <pre className="mb-4 max-w-full overflow-x-auto last:mb-0">{children}</pre>,

    // Blockquotes
    blockquote: ({ children }) => (
      <blockquote className="mb-4 border-l-4 border-cyan-400/30 bg-zinc-800/40 pl-4 py-2 italic text-zinc-300 last:mb-0">
        {children}
      </blockquote>
    ),

    // Tables
    table: ({ children }) => (
      <div className="mb-4 overflow-x-auto last:mb-0">
        <table className="min-w-full border-collapse border border-zinc-700">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-zinc-800">{children}</thead>
    ),
    tbody: ({ children }) => <tbody>{children}</tbody>,
    tr: ({ children }) => (
      <tr className="border-b border-zinc-700 last:border-b-0">{children}</tr>
    ),
    th: ({ children }) => (
      <th className="px-4 py-2 text-left text-sm font-semibold text-zinc-100">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="px-4 py-2 text-sm text-zinc-200">{children}</td>
    ),

    // Horizontal rule
    hr: () => <hr className="my-6 border-zinc-700" />,

    // Links
    a: ({ href, children }) => (
      <a
        href={href}
        className="text-cyan-400 underline hover:text-cyan-300"
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    ),
  };

  return (
    <div className="markdown-content min-w-0 break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
