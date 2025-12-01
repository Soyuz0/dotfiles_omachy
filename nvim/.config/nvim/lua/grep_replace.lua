-- lua/grep_replace.lua
-- Grep → Quickfix → Replace (per-match confirm or replace-all)

local M = {}

-- ---------- escaping ----------
local function esc_pattern_for_vim(pat)
  pat = tostring(pat or ""):gsub("\\", "\\\\"):gsub("#", "\\#")
  return "\\V" .. pat
end

local function esc_repl_for_vim(repl)
  repl = tostring(repl or ""):gsub("\\", "\\\\"):gsub("&", "\\&"):gsub("#", "\\#")
  return repl
end

-- flags: string like "gce" or "gcI"
local function cfdo_substitute(pattern, replacement, flags, close_buffers)
  flags = flags or "gce"
  local cmd = string.format([[cfdo %%s#%s#%s#%s | update]], pattern, replacement, flags)
  if close_buffers then
    cmd = cmd .. [[ | bufdo! if &modified == 0 | bd | endif]]
  end
  vim.cmd(cmd)
end

-- ---------- main ----------
local function run_picker(opts, mode)
  -- mode = "confirm" (per-match) | "all" (no confirm)
  opts = opts or {}
  local ok_b, builtin = pcall(require, "telescope.builtin")
  local ok_a, actions = pcall(require, "telescope.actions")
  local ok_s, action_state = pcall(require, "telescope.actions.state")
  if not (ok_b and ok_a and ok_s) then
    vim.notify("telescope.nvim is required", vim.log.levels.ERROR)
    return
  end

  builtin.live_grep(vim.tbl_extend("force", opts, {
    prompt_title = "Grep → Replace  (<C-r> confirm | <C-e> all | <C-q> QF only)",
    attach_mappings = function(bufnr, map)
      local function send_qf_open()
        actions.smart_send_to_qflist(bufnr)
        actions.open_qflist(bufnr)
      end

      local function do_flow(confirm_each)
        local query = action_state.get_current_line()
        if not query or query == "" then
          vim.notify("Empty search query", vim.log.levels.WARN); return
        end
        send_qf_open()
        local picker = action_state.get_current_picker(bufnr)
        if picker and picker.close then picker:close() else pcall(actions.close, bufnr) end

        vim.schedule(function()
          local replacement = vim.fn.input({ prompt = confirm_each and "Replace with (confirm each): " or "Replace with (all): " })
          if replacement == nil then return end
          local pat = esc_pattern_for_vim(query)
          local repl = esc_repl_for_vim(replacement)
          local flags = (confirm_each and "gc" or "g") .. "e"
          local ok, err = pcall(
            cfdo_substitute,
            pat, repl, flags, vim.g.grep_replace_close_buffers == 1
          )
          if not ok then
            vim.notify("cfdo failed: " .. tostring(err), vim.log.levels.ERROR); return
          end
          vim.g._grep_replace_last = { search = query, replace = replacement, confirm = confirm_each }
          if confirm_each then
            vim.notify(("Confirming each match: %q → %q"):format(query, replacement))
          else
            vim.notify(("Replaced all: %q → %q"):format(query, replacement))
          end
        end)
      end

      -- Quickfix only
      map("i", "<C-q>", function() send_qf_open() end)

      -- Confirm each match
      map("i", "<C-r>", function() do_flow(true) end)

      -- Replace all (no confirm). Alt/Meta+R (⌥R) on macOS terminals.
      map("i", "<C-e>", function() do_flow(false) end)

      -- If user invoked via command variant, run immediately after picker opens
      if mode == "confirm" then
        vim.defer_fn(function() do_flow(true) end, 10)
      elseif mode == "all" then
        vim.defer_fn(function() do_flow(false) end, 10)
      end

      return true
    end,
  }))
end

function M.grep_replace_confirm(opts)  run_picker(opts, "confirm") end
function M.grep_replace_all(opts)      run_picker(opts, "all")     end
function M.grep_replace(opts)          run_picker(opts, nil)        end

function M.setup(opts)
  opts = opts or {}
  vim.g.grep_replace_close_buffers = opts.close_buffers and 1 or 0

  vim.api.nvim_create_user_command("GrepReplace", function()
    M.grep_replace({})
  end, { desc = "Telescope live_grep → QF → choose <C-r>/<C-e>" })

  vim.api.nvim_create_user_command("GrepReplaceConfirm", function()
    M.grep_replace_confirm({})
  end, { desc = "Telescope live_grep → QF → %s#…#…#gc | update (confirm each)" })

  vim.api.nvim_create_user_command("GrepReplaceAll", function()
    M.grep_replace_all({})
  end, { desc = "Telescope live_grep → QF → %s#…#…#ge | update (replace all)" })

  vim.api.nvim_create_user_command("GrepReplaceRepeat", function()
    local last = rawget(vim.g, "_grep_replace_last")
    if not last or not last.search then
      vim.notify("No previous GrepReplace session found", vim.log.levels.WARN); return
    end
    local flags = (last.confirm and "gc" or "g") .. "e"
    local ok, err = pcall(
      cfdo_substitute,
      esc_pattern_for_vim(last.search),
      esc_repl_for_vim(last.replace or ""),
      flags,
      vim.g.grep_replace_close_buffers == 1
    )
    if not ok then
      vim.notify("cfdo failed: " .. tostring(err), vim.log.levels.ERROR); return
    end
    vim.notify(string.format("Repeated on quickfix (%s): %q → %q", last.confirm and "confirm" or "all", last.search, last.replace or ""))
  end, { desc = "Repeat last GrepReplace over current quickfix files" })
end

return M
