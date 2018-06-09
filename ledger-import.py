import csv, sys, re, collections, readline
from fuzzywuzzy import process
from account_completer import AccountCompleter

def get_string_without_comment(str):
    return re.split("(?:  | *\t+);", str)[0]

def get_account_from_user(completer):
    """
    Asks user for the name of an account, adding it to our list of accounts in
    our auto completer.
    """
    account_name = input("Enter account name: ")
    account_name = account_name.strip()
    amount = ''

    if account_name:
        completer.add_account(account_name)
        amount = input("Enter amount: ")
        # TODO: verify amount is in correct format

    return account_name, amount

def handle_split(completer):
    account_info = dict()
    next_account, amount = get_account_from_user(completer)
    while next_account:
        # TODO: should we warn user here in case they messed it up?
        if not next_account in account_info:
            account_info[next_account] = amount
        else:
            account_info[next_account] += "+" + amount
        next_account, amount = get_account_from_user(completer)

    print(account_info)
    return account_info

def get_match_selection(completer, closest_match, associated_accounts):
    """
    Returns a dictionary mapping account names to the amount associated with
    that account for this transaction.
    """
    # start index at 1 for more user-friendliness
    i = 1
    top_accounts = associated_accounts[closest_match].most_common(9)
    for acc in top_accounts:
        print(i, ":", acc[0])
        i += 1

    print("o : Other...")
    print("s : Split...")

    selection = input("Enter selection: ")
    if selection == 's':
        account_info = handle_split(completer)
    elif selection == 'o':
        # TODO: should this just be handle_split?
        account_info = dict()
        account_name, amount = get_account_from_user(completer)
        account_info[account_name] = amount
    else:
        account_info = dict()
        selected_index = int(selection)
        account_info[top_accounts[selected_index-1][0]] = ''

    return account_info


def get_accounts(account_completer, desc, associated_accounts, match_threshold=75):
    closest_match, match_score = process.extractOne(desc, associated_accounts.keys())
    print("cloest previous match: ", closest_match)

    if match_score >= match_threshold:
        accounts = get_match_selection(account_completer, closest_match, associated_accounts)
        associated_accounts[desc].update(accounts.keys())
    else:
        print("Could not find a previous transaction that is a close match.")
        accounts = dict()
        account_name, amount = get_account_from_user(account_completer)
        associated_accounts[desc] = account_name
        accounts[account_name] = amount;

    return accounts

def read_bank_transactions(account_completer, this_account, associated_accounts):
    with open('test.csv', newline='') as csv_file:
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

        # TODO: handle when debit and credit are a single column with +/-

        if csv_has_header:
            start_index = 1
        else:
            start_index = 0

        transactions = []
        for entry in rows[start_index:]:
            print(" ".join(entry[i] for i in [date_col, desc_col, debit_col, credit_col]))
            transaction = dict()
            transaction['date'] = entry[date_col]
            transaction['description'] = entry[desc_col]

            accounts = dict()
            # TODO make sure don't have both debit and credit 
            if entry[debit_col]:
                accounts[this_account] = "$-" + entry[debit_col]
            else:
                accounts[this_account] = "$" + entry[credit_col]

            x = get_accounts(account_completer, entry[desc_col], associated_accounts)
            accounts.update(x)

            transaction['accounts'] = accounts
            #print(transaction)
            transactions.append(transaction)

        return transactions

def read_ledger_entries(this_account):
    all_accounts = set()
    associated_accounts = dict()
    with open('ledger-file.dat') as ledger_file:
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
    s = transaction['date'] + " " + transaction['description'] + "\n";
    for acc, amt in transaction['accounts'].items():
        s += "\t" + acc + "\t\t" + amt + "\n"
    return s


if __name__ == "__main__":
    all_accounts, assoc_accounts = read_ledger_entries("Liabilities:CapitalOne")

    completer = AccountCompleter(list(all_accounts))
    #readline.set_completer_delims(':')
    readline.set_completer(completer.complete)
    readline.parse_and_bind('tab: complete')

    new_transactions = read_bank_transactions(completer, "Liabilities:CapitalOne", assoc_accounts)

    for nt in new_transactions:
        print(get_printable_string(nt))
