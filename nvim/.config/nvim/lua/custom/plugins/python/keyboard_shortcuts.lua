vim.keymap.set('n', '<leader>im', function()
  local pos = vim.api.nvim_win_get_cursor(0) -- save current position
  vim.cmd 'normal! G' -- go to end of file
  local lines = {
    '',
    'if __name__ == "__main__":',
    '    pytest.main(["-svv", __file__])',
  }
  vim.api.nvim_put(lines, 'l', true, true)
  vim.api.nvim_win_set_cursor(0, pos) -- restore position
end, { desc = 'Insert pytest main block at EOF and return' })
return {}
