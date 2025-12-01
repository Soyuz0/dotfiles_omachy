-- ~/.config/nvim/lua/plugins/harpoon.lua   -- LazyVim-style spec
return {
  'ThePrimeagen/harpoon',
  branch = 'harpoon2', -- make sure you’re on v2
  dependencies = { 'nvim-lua/plenary.nvim' },
  opts = {}, -- let Harpoon init itself
  config = function()
    local harpoon = require 'harpoon'
    local list = harpoon:list()

    --------------------------------------------------------------------------
    -- util: current title for slot i
    --------------------------------------------------------------------------
    local function fname(i)
      local item = (list.items or {})[i]
      return item and vim.fn.fnamemodify(item.value, ':~:.') or '<empty>'
    end

    --------------------------------------------------------------------------
    -- (re)bind <leader>1-5 with fresh desc
    --------------------------------------------------------------------------
    local function refresh_keys()
      -- wipe old <leader>1-9 bindings
      for i = 1, 9 do
        pcall(vim.keymap.del, 'n', ('<CR>%d'):format(i))
      end

      -- bind only existing items
      for i, item in ipairs(list.items or {}) do
        if i > 9 then
          break
        end
        local lhs = ('<CR>%d'):format(i)
        local desc = item.value and vim.fn.fnamemodify(item.value, ':~:.') or '<empty>'
        vim.keymap.set('n', lhs, function()
          list:select(i)
        end, { desc = ('Harpoon %d → %s'):format(i, desc), noremap = true, silent = true })
      end
    end
    refresh_keys()

    --------------------------------------------------------------------------
    -- wrap add-file so keys update instantly
    --------------------------------------------------------------------------
    vim.keymap.set('n', '<CR>f', function()
      list:add()
      refresh_keys()
    end, { desc = 'Harpoon: add file' })
    vim.keymap.set('n', '<CR>e', function()
      harpoon.ui:toggle_quick_menu(harpoon:list())
    end, { desc = 'Harpoon: Toggle quick menu' })
    --------------------------------------------------------------------------
    -- when the quick-menu closes, titles may have changed → refresh
    --------------------------------------------------------------------------
    vim.api.nvim_create_autocmd('BufWinLeave', {
      pattern = '*',
      callback = function(ev)
        if vim.bo[ev.buf].filetype == 'harpoon' then
          refresh_keys()
        end
      end,
    })
  end,
}
