-- Portable dictionary plus machine-local words. Never append to tracked files.
local M = {}
local ready = false

local function paths()
  local state = vim.fn.stdpath 'state' .. '/cspell'
  return state, state .. '/cspell.json', state .. '/custom-words.txt'
end

function M.config_path()
  local state, config, words = paths()
  if ready then
    return config
  end
  vim.fn.mkdir(state, 'p')
  if vim.fn.filereadable(words) == 0 then
    assert(vim.fn.writefile({}, words) == 0, 'Cannot create local cspell dictionary')
  end
  local imports = { vim.fn.stdpath 'config' .. '/cspell.json' }
  -- Preserve existing external dictionaries without copying their private words.
  for _, path in ipairs {
    vim.fn.expand '~/.config/cspell.json',
    vim.fn.stdpath 'config' .. '/cspell.local.json',
  } do
    if vim.fn.filereadable(path) == 1 then
      table.insert(imports, path)
    end
  end
  local settings = {
    version = '0.2',
    import = imports,
    dictionaryDefinitions = { { name = 'machine-local-words', path = words, addWords = true } },
    dictionaries = { 'machine-local-words' },
  }
  assert(vim.fn.writefile({ vim.json.encode(settings) }, config) == 0, 'Cannot write local cspell config')
  ready = true
  return config
end

function M.add_word(word)
  assert(type(word) == 'string' and word ~= '' and not word:find '[\r\n]', 'Invalid dictionary word')
  M.config_path()
  local _, _, words = paths()
  local entries = vim.fn.readfile(words)
  table.insert(entries, word)
  table.sort(entries)
  local unique = {}
  for _, entry in ipairs(entries) do
    if entry ~= '' and entry ~= unique[#unique] then
      table.insert(unique, entry)
    end
  end
  assert(vim.fn.writefile(unique, words) == 0, 'Cannot update local cspell dictionary')
end

return M
