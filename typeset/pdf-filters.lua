-- Pandoc filter for PDF builds (bin/make-pdf includes it).

-- Obsidian's manual page break, <div style="page-break-after: always;"></div>,
-- arrives as a Div (pandoc parses a bare <div> natively), so catch Div, not RawBlock.
function Div(el)
  if el.attributes.style and el.attributes.style:find("page%-break") then
    return pandoc.RawBlock("latex", "\\clearpage")
  end
end

-- LaTeX cannot include SVG. Use a PDF beside it when one exists.
function Image(el)
  if el.src:match("%.svg$") then
    local pdf = el.src:gsub("%.svg$", ".pdf")
    local f = io.open(pdf, "r")
    if f then
      f:close()
      el.src = pdf
    end
  end
  return el
end

-- References: on a new page (unless the front matter sets
-- references-page-break: false), under a "References" heading. Runs after
-- citeproc (make-pdf orders --citeproc before this filter), which puts the
-- list in a Div with id "refs". A heading the author already wrote is kept.
local function stringify(el) return pandoc.utils.stringify(el) end

function Pandoc(doc)
  local blocks = doc.blocks
  local at
  for i, b in ipairs(blocks) do
    if b.t == "Div" and b.identifier == "refs" and #b.content > 0 then at = i break end
  end
  if not at then return nil end
  local prev = blocks[at - 1]
  local titled = prev and prev.t == "Header"
    and stringify(prev):lower():match("^%s*references%s*$")
  -- Front matter "references-page-break: false" keeps the references on the
  -- same page as the text before them.
  local want_break = doc.meta["references-page-break"] ~= false
  local brk = pandoc.RawBlock("latex", want_break and "\\clearpage" or "")
  if titled then
    blocks:insert(at - 1, brk)
  else
    -- Use the document's section level: 2 under a single H1 title, else 1.
    local h1, first = 0, nil
    for _, b in ipairs(blocks) do
      if b.t == "Header" then
        first = first or b
        if b.level == 1 then h1 = h1 + 1 end
      end
    end
    local level = (first and first.level == 1 and h1 == 1) and 2 or 1
    blocks:insert(at, pandoc.Header(level, "References", pandoc.Attr("references", {"unnumbered"})))
    blocks:insert(at, brk)
  end
  return pandoc.Pandoc(blocks, doc.meta)
end
