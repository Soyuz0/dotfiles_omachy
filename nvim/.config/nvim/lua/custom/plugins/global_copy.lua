return {
  'ojroques/nvim-osc52',
  opts = {},
  config = function()
    require('osc52').setup {
      max_length = 0,
      trim = false,
      silent = false,
    }
    local osc52 = require 'osc52'
    vim.keymap.set('n', '<leader>cc', osc52.copy_operator, { expr = true, desc = 'OSC52 copy (operator/motion)' })

    vim.keymap.set('n', '<leader>cf', function()
      require('osc52').copy(vim.fn.expand '%:p')
    end, { desc = 'OSC52 copy file path to clipboard' })
    vim.keymap.set({ 'x', 'v' }, '<leader>cc', osc52.copy_visual, { desc = 'OSC52 copy (visual)' })
  end,
}
