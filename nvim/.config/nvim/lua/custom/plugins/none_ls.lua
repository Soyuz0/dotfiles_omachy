return {
  'nvimtools/none-ls.nvim',
  dependencies = {
    'nvimtools/none-ls-extras.nvim',
    'jayp0521/mason-null-ls.nvim', -- ensure dependencies are installed
    'davidmh/cspell.nvim',
  },
  config = function()
    local null_ls = require 'null-ls'
    local formatting = null_ls.builtins.formatting -- to setup formatters
    local diagnostics = null_ls.builtins.diagnostics -- to setup linters
    local cspell = require 'cspell'

    local cspell_config = {
      find_json = function(_)
        return vim.fn.expand '~/.config/cspell.json'
      end,
    } -- list of formatters & linters for mason to install
    require('mason-null-ls').setup {
      ensure_installed = {
        'checkmake',
        'prettier', -- ts/js formatter
        'stylua', -- lua formatter
        'shfmt',
        'ruff',
        'cspell',
      },
      -- auto-install configured formatters & linters (with null-ls)
      automatic_installation = true,
    }

    local sources = {
      diagnostics.checkmake,
      formatting.prettier.with { filetypes = { 'json', 'yaml', 'markdown' } },
      formatting.stylua,
      formatting.shfmt.with { args = { '-i', '4' } },
      formatting.terraform_fmt,
      require('none-ls.formatting.ruff').with { extra_args = { '--extend-select', 'I' } },
      require 'none-ls.formatting.ruff_format',
    }
    table.insert(
      sources,
      cspell.diagnostics.with {
        filetypes = { 'lua', 'python', 'markdown', 'javascript', 'typescript', 'txt' },
        diagnostics_postprocess = function(diagnostic)
          diagnostic.severity = vim.diagnostic.severity.HINT
        end,
        config = cspell_config,
      }
    )

    table.insert(sources, cspell.code_actions.with { config = cspell_config })
    local augroup = vim.api.nvim_create_augroup('LspFormatting', {})
    null_ls.setup {
      -- debug = true, -- Enable debug mode. Inspect logs with :NullLsLog.
      sources = sources,
      -- you can reuse a shared lspconfig on_attach callback here
      on_attach = function(client, bufnr)
        if client.supports_method 'textDocument/formatting' then
          vim.api.nvim_clear_autocmds { group = augroup, buffer = bufnr }
          vim.api.nvim_create_autocmd('BufWritePre', {
            callback = function()
              vim.lsp.buf.format {
                async = true,
                filter = function(c)
                  return c.name == 'null-ls'
                end,
              }
            end,
          })
        end
      end,
    }
  end,
}
