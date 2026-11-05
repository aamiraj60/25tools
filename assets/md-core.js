/* Markdown to HTML parser for the converter page.
 *
 * The page offers a "Strip <script>" switch, which only makes sense if raw
 * HTML is allowed through by default, so a block of HTML passes through as it
 * is and the switch removes the dangerous parts. Text outside HTML is escaped.
 *
 * Pure functions, no DOM, so the parser can be tested on its own.
 */
(function (root) {
  var HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
  var FENCE = /^\s*(```|~~~)\s*([\w+#.-]*)\s*$/;
  var HR = /^\s*([-*_])(\s*\1){2,}\s*$/;
  var QUOTE = /^\s*>\s?/;
  var LIST = /^\s*([-*+]|\d+\.)\s+/;
  var BLANK = /^\s*$/;
  var INDENT = /^( {4,}|\t)/;
  var RAW_TAG = /^\s*<\/?[a-zA-Z][\w-]*(\s[^<>]*)?\/?>\s*$/;
  var RAW_OPEN = /^\s*<(script|style|pre|div|table|details|section|iframe|figure|video|svg|textarea)\b/i;

  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function inline(text) {
    var codes = [];
    var out = String(text).replace(/`([^`]+)`/g, function (_, code) {
      codes.push(code);
      return "\u0000C" + (codes.length - 1) + "\u0000";
    });
    out = escapeHtml(out);
    out = out.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, function (_, alt, src) {
      return '<img src="' + src + '" alt="' + alt + '" loading="lazy">';
    });
    out = out.replace(/\[([^\]]*)\]\(([^)\s]+)\)/g, function (_, label, href) {
      return '<a href="' + href + '" rel="noopener">' + label + "</a>";
    });
    out = out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    out = out.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    out = out.replace(/(^|[^*\w])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    out = out.replace(/(^|[^_\w])_([^_\n]+)_/g, "$1<em>$2</em>");
    out = out.replace(/\u0000C(\d+)\u0000/g, function (_, n) {
      return "<code>" + escapeHtml(codes[Number(n)]) + "</code>";
    });
    return out;
  }

  function isTableHead(line, next) {
    return line.indexOf("|") >= 0 && /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(next || "");
  }

  function tableCells(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "")
      .split("|").map(function (c) { return c.trim(); });
  }

  function isRawStart(line) {
    return RAW_TAG.test(line) || RAW_OPEN.test(line);
  }

  /* Raw HTML runs from an opening tag to the line that closes it. A single
   * self-contained line counts as the whole block. */
  function rawBlock(lines, start) {
    var open = lines[start].match(/<([a-zA-Z][\w-]*)/);
    if (!open) return 1;
    var tag = open[1].toLowerCase();
    if (new RegExp("</" + tag + "\\s*>", "i").test(lines[start])) return 1;
    for (var j = start + 1; j < lines.length; j++) {
      if (new RegExp("</" + tag + "\\s*>", "i").test(lines[j])) return j - start + 1;
    }
    return 1;
  }

  function stripUnsafe(html) {
    return html
      .replace(/<script\b[^>]*>[\s\S]*?<\/script\s*>/gi, "")
      .replace(/<iframe\b[^>]*>[\s\S]*?<\/iframe\s*>/gi, "")
      .replace(/\son\w+\s*=\s*"[^"]*"/gi, "")
      .replace(/\son\w+\s*=\s*'[^']*'/gi, "")
      .replace(/\son\w+\s*=\s*[^\s>]+/gi, "")
      .replace(/(href|src)\s*=\s*(["'])\s*javascript:[^"']*\2/gi, "$1=$2#$2");
  }

  function addTailwind(html) {
    return html
      .replace(/<h1>/g, '<h1 class="text-3xl font-bold">')
      .replace(/<h2>/g, '<h2 class="text-2xl font-semibold">')
      .replace(/<h3>/g, '<h3 class="text-xl font-semibold">')
      .replace(/<p>/g, '<p class="my-4 leading-relaxed">')
      .replace(/<ul>/g, '<ul class="list-disc pl-6">')
      .replace(/<ol>/g, '<ol class="list-decimal pl-6">')
      .replace(/<blockquote>/g, '<blockquote class="border-l-4 pl-4 italic">')
      .replace(/<pre>/g, '<pre class="rounded-lg p-4 overflow-x-auto">');
  }

  function renderMarkdown(src, opts) {
    opts = opts || {};
    var lines = String(src).replace(/\r\n?/g, "\n").split("\n");
    var out = [];
    var i = 0;

    while (i < lines.length) {
      var line = lines[i];
      var m;

      var fence = line.match(FENCE);
      if (fence) {
        var close = fence[1];
        var lang = fence[2];
        var buf = [];
        i++;
        while (i < lines.length && !new RegExp("^\\s*" + close + "\\s*$").test(lines[i])) {
          buf.push(lines[i]);
          i++;
        }
        i++;
        out.push('<pre><code' + (lang ? ' class="language-' + lang + '"' : "") + ">"
          + escapeHtml(buf.join("\n")) + "</code></pre>");
        continue;
      }

      m = line.match(HEADING);
      if (m) {
        var lvl = m[1].length;
        out.push("<h" + lvl + ">" + inline(m[2]) + "</h" + lvl + ">");
        i++;
        continue;
      }

      if (HR.test(line)) { out.push("<hr>"); i++; continue; }

      if (QUOTE.test(line)) {
        var q = [];
        while (i < lines.length && QUOTE.test(lines[i])) {
          q.push(lines[i].replace(QUOTE, ""));
          i++;
        }
        out.push("<blockquote>" + renderMarkdown(q.join("\n"), opts) + "</blockquote>");
        continue;
      }

      if (isTableHead(line, lines[i + 1])) {
        var head = tableCells(line);
        i += 2;
        var rows = [];
        while (i < lines.length && lines[i].indexOf("|") >= 0 && !BLANK.test(lines[i])) {
          rows.push(tableCells(lines[i]));
          i++;
        }
        var t = "<table><thead><tr>";
        head.forEach(function (h) { t += "<th>" + inline(h) + "</th>"; });
        t += "</tr></thead><tbody>";
        rows.forEach(function (r) {
          t += "<tr>";
          head.forEach(function (_, n) { t += "<td>" + inline(r[n] || "") + "</td>"; });
          t += "</tr>";
        });
        out.push(t + "</tbody></table>");
        continue;
      }

      if (LIST.test(line)) {
        var ordered = /^\s*\d+\.\s+/.test(line);
        var items = [];
        while (i < lines.length && LIST.test(lines[i])) {
          var raw = lines[i].replace(LIST, "");
          var task = raw.match(/^\[([ xX])\]\s+(.*)$/);
          if (task) {
            items.push('<li class="task-item"><input type="checkbox" disabled'
              + (task[1].toLowerCase() === "x" ? " checked" : "") + "><span>"
              + inline(task[2]) + "</span></li>");
          } else {
            items.push("<li>" + inline(raw) + "</li>");
          }
          i++;
        }
        var tag = ordered ? "ol" : "ul";
        out.push("<" + tag + ">" + items.join("") + "</" + tag + ">");
        continue;
      }

      if (INDENT.test(line)) {
        var code = [];
        while (i < lines.length && (INDENT.test(lines[i]) || BLANK.test(lines[i]))) {
          code.push(lines[i].replace(INDENT, ""));
          i++;
        }
        while (code.length && BLANK.test(code[code.length - 1])) code.pop();
        out.push("<pre><code>" + escapeHtml(code.join("\n")) + "</code></pre>");
        continue;
      }

      if (BLANK.test(line)) { i++; continue; }

      if (isRawStart(line)) {
        var n = rawBlock(lines, i);
        out.push(lines.slice(i, i + n).join("\n"));
        i += n;
        continue;
      }

      var para = [];
      while (i < lines.length && !BLANK.test(lines[i]) && !FENCE.test(lines[i])
        && !HEADING.test(lines[i]) && !QUOTE.test(lines[i]) && !LIST.test(lines[i])
        && !HR.test(lines[i]) && !INDENT.test(lines[i])
        && !isRawStart(lines[i]) && !isTableHead(lines[i], lines[i + 1])) {
        para.push(lines[i]);
        i++;
      }
      out.push("<p>" + para.map(inline).join("<br>") + "</p>");
    }

    var html = out.join("\n");
    if (opts.strip) html = stripUnsafe(html);
    if (opts.tailwind) html = addTailwind(html);
    if (opts.minify) html = html.replace(/\n{2,}/g, "\n").replace(/>\s+</g, "><").trim();
    return html;
  }

  var api = {
    escapeHtml: escapeHtml,
    inline: inline,
    renderMarkdown: renderMarkdown,
    stripUnsafe: stripUnsafe,
    addTailwind: addTailwind
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.MD = api;
})(typeof window !== "undefined" ? window : this);
