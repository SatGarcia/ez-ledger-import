import csv, sys, re, collections, readline
from fuzzywuzzy import process
from account_completer import AccountCompleter

def get_string_without_comment(str):
    return re.split("(?:  | *\t+);", str)[0]

def get_accounts(desc, associated_accounts, match_threshold=75):
    accounts = dict()
    closest_match, match_score = process.extractOne(desc, associated_accounts.keys())
    print("cloest previous match: ", closest_match)

    if match_score >= match_threshold:
        # start index at 1 for more user-friendliness
        i = 1
        top_accounts = associated_accounts[closest_match].most_common(9)
        for acc in top_accounts:
            print(i, ":", acc[0])
            i += 1

        selected_index = int(input("enter selection: "))
        account_name = top_accounts[selected_index-1][0]
        associated_accounts[desc].update([account_name])
    else:
        print("Could not find a previous transaction that is a close match.")
        account_name = input("Enter account name: ")
        associated_accounts[desc] = account_name

    accounts[account_name] = "";
    return accounts

def read_bank_transactions(this_account, associated_accounts):
    with open('test.csv', newline='') as csv_file:
        csv_has_header = csv.Sniffer().has_header(csv_file.read(1024))
        csv_file.seek(0)

        csv_reader = csv.reader(csv_file)
        rows = []
        for row in csv_reader:
            print(row)
            rows += [row]

        """
        print(rows)
        for e in rows:
            print(e)
        """

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

            x = get_accounts(entry[desc_col], associated_accounts)
            accounts.update(x)

            transaction['accounts'] = accounts
            print(transaction)
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

if __name__ == "__main__":
    all_accounts, assoc_accounts = read_ledger_entries("Liabilities:CapitalOne")

    completer = AccountCompleter(list(all_accounts))
    #readline.set_completer_delims(':')
    readline.set_completer(completer.complete)
    readline.parse_and_bind('tab: complete')

    new_transactions = read_bank_transactions("Liabilities:CapitalOne", assoc_accounts)

    for nt in new_transactions:
        print("\n")
        for k,v in nt.items():
            print(k, ":", v)

    """
    for k,v in assoc_accounts.items():
        print("\npayee:", k)
        print("accounts:")
        for acc in v.most_common(9):
            print("\t", acc[0])
    """
