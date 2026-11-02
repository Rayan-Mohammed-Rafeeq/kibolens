import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MarkdownRenderer } from "./markdown-renderer";

describe("MarkdownRenderer", () => {
  it("renders headings H1-H6", () => {
    const markdown = `
# Heading 1
## Heading 2
### Heading 3
#### Heading 4
##### Heading 5
###### Heading 6
    `.trim();

    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByRole("heading", { level: 1, name: "Heading 1" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Heading 2" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 3, name: "Heading 3" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 4, name: "Heading 4" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 5, name: "Heading 5" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 6, name: "Heading 6" })).toBeTruthy();
  });

  it("renders bold text", () => {
    const markdown = "This is **bold text** in a sentence.";
    const { container } = render(<MarkdownRenderer content={markdown} />);
    
    const strong = container.querySelector("strong");
    expect(strong).toBeTruthy();
    expect(strong?.textContent).toBe("bold text");
  });

  it("renders italic text", () => {
    const markdown = "This is *italic text* in a sentence.";
    const { container } = render(<MarkdownRenderer content={markdown} />);
    
    const em = container.querySelector("em");
    expect(em).toBeTruthy();
    expect(em?.textContent).toBe("italic text");
  });

  it("renders unordered lists", () => {
    const markdown = `
- Item 1
- Item 2
- Item 3
    `.trim();

    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByText("Item 1")).toBeTruthy();
    expect(screen.getByText("Item 2")).toBeTruthy();
    expect(screen.getByText("Item 3")).toBeTruthy();
  });

  it("renders ordered lists", () => {
    const markdown = `
1. First item
2. Second item
3. Third item
    `.trim();

    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByText("First item")).toBeTruthy();
    expect(screen.getByText("Second item")).toBeTruthy();
    expect(screen.getByText("Third item")).toBeTruthy();
  });

  it("renders nested lists", () => {
    const markdown = `
- Parent item
  - Nested item 1
  - Nested item 2
- Another parent
    `.trim();

    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByText("Parent item")).toBeTruthy();
    expect(screen.getByText("Nested item 1")).toBeTruthy();
    expect(screen.getByText("Nested item 2")).toBeTruthy();
    expect(screen.getByText("Another parent")).toBeTruthy();
  });

  it("renders inline code", () => {
    const markdown = "Use the `console.log()` function.";
    const { container } = render(<MarkdownRenderer content={markdown} />);
    
    const code = container.querySelector("code");
    expect(code).toBeTruthy();
    expect(code?.textContent).toBe("console.log()");
  });

  it("renders code blocks", () => {
    const markdown = `
\`\`\`javascript
function hello() {
  console.log("Hello");
}
\`\`\`
    `.trim();

    const { container } = render(<MarkdownRenderer content={markdown} />);
    
    const code = container.querySelector("code");
    expect(code).toBeTruthy();
    expect(code?.textContent).toContain("function hello()");
    expect(code?.textContent).toContain('console.log("Hello")');
  });

  it("renders tables with headers and rows", () => {
    const markdown = `
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Cell 1   | Cell 2   | Cell 3   |
| Cell 4   | Cell 5   | Cell 6   |
    `.trim();

    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByText("Column 1")).toBeTruthy();
    expect(screen.getByText("Column 2")).toBeTruthy();
    expect(screen.getByText("Column 3")).toBeTruthy();
    expect(screen.getByText("Cell 1")).toBeTruthy();
    expect(screen.getByText("Cell 4")).toBeTruthy();
  });

  it("renders blockquotes", () => {
    const markdown = "> This is a blockquote";
    const { container } = render(<MarkdownRenderer content={markdown} />);
    
    const blockquote = container.querySelector("blockquote");
    expect(blockquote).toBeTruthy();
    expect(blockquote?.textContent).toContain("This is a blockquote");
  });

  it("renders links with target blank", () => {
    const markdown = "Visit [example](https://example.com)";
    render(<MarkdownRenderer content={markdown} />);
    
    const link = screen.getByRole("link", { name: "example" }) as HTMLAnchorElement;
    expect(link).toBeTruthy();
    expect(link.href).toBe("https://example.com/");
    expect(link.target).toBe("_blank");
    expect(link.rel).toBe("noopener noreferrer");
  });

  it("renders horizontal rules", () => {
    const markdown = `
Before rule

---

After rule
    `.trim();

    const { container } = render(<MarkdownRenderer content={markdown} />);
    
    const hr = container.querySelector("hr");
    expect(hr).toBeTruthy();
  });

  it("renders paragraphs with proper spacing", () => {
    const markdown = `
First paragraph with some text.

Second paragraph with more text.

Third paragraph.
    `.trim();

    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByText("First paragraph with some text.")).toBeTruthy();
    expect(screen.getByText("Second paragraph with more text.")).toBeTruthy();
    expect(screen.getByText("Third paragraph.")).toBeTruthy();
  });

  it("handles mixed formatting", () => {
    const markdown = `
## Analysis

The system shows **high CPU usage** with the following metrics:

- CPU: *85%*
- Memory: \`8.2GB\`
- Disk: **92%**

### Recommendations

1. Scale horizontally
2. Optimize queries
3. Review \`database.config\`
    `.trim();

    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByRole("heading", { level: 2, name: "Analysis" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 3, name: "Recommendations" })).toBeTruthy();
    expect(screen.getByText("Scale horizontally")).toBeTruthy();
    expect(screen.getByText("Optimize queries")).toBeTruthy();
  });

  it("handles malformed markdown gracefully", () => {
    const markdown = "**Unclosed bold";
    const { container } = render(<MarkdownRenderer content={markdown} />);
    
    // Should still render without crashing
    expect(container.textContent).toContain("Unclosed bold");
  });

  it("handles empty content", () => {
    const { container } = render(<MarkdownRenderer content="" />);
    expect(container.textContent).toBe("");
  });

  it("renders the complete long response without clipping its content", () => {
    const content = "## Infrastructure status\n\n" + ("Observed evidence line.\n".repeat(400));
    const { container } = render(<MarkdownRenderer content={content} />);

    expect(container.textContent).toContain("Observed evidence line.");
    expect(container.textContent?.length).toBeGreaterThan(content.length - 20);
    expect(container.firstElementChild?.className).toContain("break-words");
  });

  it("handles special characters in code", () => {
    const markdown = "Use \`<div>\` and \`&nbsp;\` entities.";
    render(<MarkdownRenderer content={markdown} />);
    
    expect(screen.getByText("<div>")).toBeTruthy();
    expect(screen.getByText("&nbsp;")).toBeTruthy();
  });

  it("renders complex nested structures", () => {
    const markdown = `
## Infrastructure Status

### Current Metrics

| Metric | Value | Status |
|--------|-------|--------|
| CPU    | 45%   | OK     |
| Memory | 78%   | **High** |
| Disk   | 92%   | **Critical** |

### Issues

1. **High disk usage**
   - Log files: \`/var/log\` at 85%
   - Database: \`/data\` at 95%
2. **Memory pressure**
   - Application: 4.2GB
   - Cache: 3.8GB

> **Warning**: Disk space critically low

### Actions

- Clean old logs
- Scale database
- Increase \`memory_limit\`
    `.trim();

    render(<MarkdownRenderer content={markdown} />);

    expect(screen.getByRole("heading", { level: 2, name: "Infrastructure Status" })).toBeTruthy();
    expect(screen.getByText("CPU")).toBeTruthy();
    expect(screen.getByText("High disk usage")).toBeTruthy();
    expect(screen.getByText(/Warning/)).toBeTruthy();
  });
});
