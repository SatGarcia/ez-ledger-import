import csv, sys, re, collections, readline
from fuzzywuzzy import process
from account_completer import AccountCompleter
from dateutil.parser import parse

def get_string_without_comment(str):
    return re.split("(?:  +| *\t+);", str)[0]

def get_account_from_user(completer, tax_amount = "1.0775"):
    """
    Asks user for the name of an account, adding it to our list of accounts in
    our auto completer.
    """
    account_name = input("Enter account name: ")
    account_name = account_name.strip()
    amount = ''

    if account_name:
        completer.add_account(account_name)
        while True:
            # TODO: print out message about space separated multiple amounts
            # and * for tax-free
            individual_amounts = input("Enter amount: ")
            individual_amounts = individual_amounts.strip()

            # If they entered something, make sure it is of the right format and
            # parse it into ledger format
            if re.fullmatch("((?:^|\s+)\d+(?:\.\d\d)?\*?)*", individual_amounts):
                if individual_amounts:
                    raw_amounts = individual_amounts.split()
                    # "*" after amount indicates it is untaxed
                    taxed_amounts = ['$' + ra + '*' + tax_amount for ra in raw_amounts if ra[-1] != '*']
                    untaxed_amounts = ['$' + ra[:-1] for ra in raw_amounts if ra[-1] == '*']
                    amount = '(' + ' + '.join(taxed_amounts + untaxed_amounts) + ')'
                break
            elif individual_amounts:
                print("Invalid amount format.")


    return account_name, amount

def handle_split(completer):
    """
    Returns a dictionary mapping accounts with associated amount, as entered
    by the user.
    """
    account_info = dict()
    next_account, amount = get_account_from_user(completer)
    while next_account:
        # TODO: should we warn user here in case they messed it up?
        if not next_account in account_info:
            account_info[next_account] = amount
        else:
            account_info[next_account] += "+" + amount
        next_account, amount = get_account_from_user(completer)

    #print(account_info)
    return account_info

def get_match_selection(completer, matches, associated_accounts):
    """
    Returns a dictionary mapping account names to the amount associated with
    that account for this transaction.
    """
    frequencies = collections.Counter()
    for m in matches:
        frequencies += associated_accounts[m]

    top_accounts = frequencies.most_common(9)

    # start index at 1 for more user-friendliness
    i = 1
    for acc in top_accounts:
        print(i, ":", acc[0])
        i += 1

    print("o : Other / Split...")

    while True:
        selection = input("\nEnter selection: ")
        if re.fullmatch("\d+", selection):
            account_info = dict()
            selected_index = int(selection)
            if selected_index > 0 and selected_index <= len(top_accounts):
                account_info[top_accounts[selected_index-1][0]] = ''
                break
            else:
                print("Invalid selection!")
        elif selection == 'o':
            account_info = handle_split(completer)
            break
        else:
            print("Invalid selection!")

    return account_info


def get_accounts(account_completer, desc, associated_accounts, match_threshold=75):
    """
    Returns dictionary that maps accounts to their associated amounts for the
    transaction with the given description.
    This also updates the list of associated accounts for desc, so we have a
    history for improving future transactions with the same or similar
    description.
    """
    desc = re.sub('PAYPAL \*|SQ \*', '', desc)
    close_matches = [name for name, score in process.extract(desc,
                                                             associated_accounts.keys())
                     if score >= match_threshold]

    if close_matches:
        accounts = get_match_selection(account_completer, close_matches, associated_accounts)
        if desc in associated_accounts:
            associated_accounts[desc].update(accounts.keys())
        else:
            associated_accounts[desc] = collections.Counter(accounts.keys())
    else:
        print("Could not find a previous transaction that is a close match.")
        accounts = handle_split(account_completer)
        associated_accounts[desc] = collections.Counter(accounts.keys())

    return accounts

def read_bank_transactions(csv_filename, account_completer, this_account, associated_accounts):
    """
    Returns a list of transactions based on a given CSV file.
    Each transaction will include the date, a description of the transaction
    (i.e. the payee), and a dictionary mapping the accounts used by this
    transaction and the amount of money associated with that account for this
    transaction.
    """
    with open(csv_filename, newline='') as csv_file:
        csv_has_header = csv.Sniffer().has_header(csv_file.read(1024))
        csv_file.seek(0)

        csv_reader = csv.reader(csv_file)
        rows = []
        for row in csv_reader:
            print(row)
            rows += [row]

        for i in range(len(rows[0])):
            print(i, ":", rows[0][i])

        date_col = int(input("Which entry contains the transaction date? "))
        desc_col = int(input("Which entry contains the description? "))
        debit_col = int(input("Which entry contains the debit amount? "))
        credit_col = int(input("Which entry contains the credit amount? "))

        combined_debit_credit = debit_col == credit_col

        if csv_has_header:
            start_index = 1
        else:
            start_index = 0

        sorted_rows = sorted(rows[start_index:],
                             key=lambda r: parse(r[date_col]))

        transactions = []
        for entry in sorted_rows:
            print()
            if combined_debit_credit:
                print(" || ".join(entry[i] for i in [date_col, desc_col, debit_col]))
            else:
                print(" || ".join(entry[i] for i in [date_col, desc_col, debit_col, credit_col]))

            transaction = dict()
            transaction['date'] = parse(entry[date_col]).strftime("%Y-%m-%d")
            transaction['description'] = entry[desc_col]

            # TODO: make sure there isn't a "$" in debit or credit column

            accounts = dict()

            if not combined_debit_credit and entry[debit_col] and entry[credit_col]:
                raise RuntimeError("Entry has both debit and credit")

            this_account_amount = "$"
            if combined_debit_credit:
                if entry[debit_col][0] == "-":
                    # "-" with combined debit/credit implies credit, i.e.
                    # positive amount for this_account
                    this_account_amount += entry[debit_col][1:]
                else:
                    # lack of "-" for combined debit/credit implies debit,
                    # i.e.  negative amount from this_account
                    this_account_amount += "-" + entry[debit_col]
            elif entry[debit_col]:
                if entry[debit_col][0] != "-":
                    this_account_amount += "-"
                this_account_amount += entry[debit_col]
            else:
                this_account_amount += entry[credit_col]

            accounts[this_account] = this_account_amount

            x = get_accounts(account_completer, entry[desc_col], associated_accounts)
            accounts.update(x)

            transaction['accounts'] = accounts
            #print(transaction)
            transactions.append(transaction)

        return transactions

def read_ledger_entries(ledger_filename, this_account):
    """
    Reads an existing ledger file and returns a list of all accounts used in
    this ledger file and a mapping between every transaction description (i.e.
    payee) and a counter of the frequency with which accounts were used in
    transactions with the same or similar description.
    """
    all_accounts = set()
    associated_accounts = dict()
    with open(ledger_filename) as ledger_file:
        in_transaction = False
        payee = ""

        for line in ledger_file:
            line = line.rstrip()
            #print(line)

            if not line:
                in_transaction = False

            elif line[0] == ' ' or line[0] == '\t':
                if not in_transaction:
                    print("Ruh roh!")
                    sys.exit(1)

                # remove leading whitespace
                line = line.lstrip()

                line_without_comment = get_string_without_comment(line)
                components = re.split("(?: *\t+|  )+", line_without_comment)
                if len(components) > 2:
                    print("invalid format:", line_without_comment)
                    sys.exit(1)

                account = components[0]
                all_accounts.add(account)
                if account != this_account:
                    #print("account:", account)
                    associated_accounts[payee].update([account])

            # this should be the start of a new transaction
            else:
                # use split to separate out the comment
                header = get_string_without_comment(line)

                # fixme: come up with more accurate regex for date
                re_match = re.match("\d+\S*\s+(?:[*!]\s+)?(?:\(\S+\)\s+)?(.*)", header)
                if not re_match:
                    print("invalid transaction header:", header)
                    sys.exit(1)

                payee = re_match.group(1)
                #print("payee:", payee)

                if not payee in associated_accounts:
                    associated_accounts[payee] = collections.Counter()

                in_transaction = True

    return all_accounts, associated_accounts

def get_printable_string(transaction):
    """
    Returns a "Ledger-style" string representation of the tranaction.
    """
    s = transaction['date'] + " " + transaction['description'] + "\n";
    for acc, amt in transaction['accounts'].items():
        s += "\t" + acc + "\t\t" + amt + "\n"

    s += "\n"   # blank line after transaction, muiy importante
    return s


def write_transactions_to_file(output_filename, transactions):
    """
    Writes given transactions out in ledger format to the specified output
    file.
    """
    with open(output_filename, "a") as output_file:
        # sort transactions by date before writing them to file
        sorted_transactions = sorted(transactions, key=lambda t: t['date'])

        for t in sorted_transactions:
            output_file.write(get_printable_string(t))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: {script} ledger_file csv_file output_file".format(script=sys.argv[0]))
        sys.exit(0)

    this_account = input("Enter the CSV file's account name: ")
    all_accounts, assoc_accounts = read_ledger_entries(sys.argv[1],
                                                       this_account)

    completer = AccountCompleter(list(all_accounts))
    readline.set_completer_delims(':')
    readline.set_completer(completer.complete)
    readline.parse_and_bind('tab: complete')

    new_transactions = read_bank_transactions(sys.argv[2], completer,
                                              this_account, assoc_accounts)

    # TODO: allow user to specify whether to append or to overwrite the output
    # file
    write_transactions_to_file(sys.argv[3], new_transactions)
