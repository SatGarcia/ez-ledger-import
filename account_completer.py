import readline

class AccountCompleter(object):  # Custom completer

    def __init__(self, accounts):
        # TODO: add partials paths for each account
        self.accounts = sorted(accounts)

    def add_account(self, new_account):
        if new_account and not new_account in self.accounts:
            self.accounts.append(new_account)
            self.accounts = sorted(self.accounts)

    def complete(self, text, state):
        buffer = readline.get_line_buffer()
        if state == 0:  # on first trigger, build possible matches
            if not buffer:
                self.matches = self.accounts[:]
            else:
                self.matches = [s for s in self.accounts
                                if s and s.startswith(buffer)]

        # return match indexed by state
        if state < len(self.matches):
            return self.matches[state][len(buffer)-len(text):]
        else:
            return None


if __name__ == "__main__":
    accounts = [
        'Expenses:Food',
        'Expenses:Music',
        'Expenses:Gas',
        'Assets:SDCCU:Checking',
        'Assets:SDCCU:Saving',
        'Liabilities:CapitalOne',
        'Liabilities:CapitalTwo',
        'Liabilities:Discover'
        ]

    completer = AccountCompleter(list(set(accounts)))
    #readline.set_completer_delims(':')
    readline.set_completer(completer.complete)
    readline.parse_and_bind('tab: complete')

    print('Enter an account name:\n\t')
    account = input("> ")
    print(account)
