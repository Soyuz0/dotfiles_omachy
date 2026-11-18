return {
  'MeanderingProgrammer/render-markdown.nvim',
  dependencies = { 'nvim-treesitter/nvim-treesitter', 'echasnovski/mini.icons' }, -- if you use standalone mini plugins
  init = function()
    if vim.fn.has 'nvim-0.12' == 1 then
      -- Legacy nvim-treesitter's fenced-code directive expects the removed
      -- single-node query API. Keep injections working with Neovim's own query.
      local query = vim.fn.readfile(vim.env.VIMRUNTIME .. '/queries/markdown/injections.scm')
      vim.treesitter.query.set('markdown', 'injections', table.concat(query, '\n'))
    end
  end,
  ---@module 'render-markdown'
  ---@type render.md.UserConfig
  opts = {},
}
