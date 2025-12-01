return {
  'tpope/vim-fugitive',
  config = function()
    -- lua/fugitive_view.lua
    vim.keymap.set('n', '<leader>gv', function()
      vim.cmd 'Git' -- open :Gstatus in current (or new) split
      -- move the Gstatus pane to far left
      vim.cmd 'wincmd H' -- equivalent to <:wincmd> + <H>
      -- resize to ~25% width
      local width = math.max(35, math.floor(vim.o.columns * 0.25))
      vim.cmd('vertical resize ' .. width)
    end, { desc = '[G]it [V]iewer' })
  end,
}
