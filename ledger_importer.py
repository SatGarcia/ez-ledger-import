import csv, sys, re, collections, readline, argparse

from tinydb import TinyDB
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
    comments = ''

    if account_name:
        completer.add_account(account_name)
        while True:
            user_input = input("Enter space-separated amounts. Append '*' to untaxed amounts: ")
            #individual_amounts = user_input.strip()

            # separate comment from the amounts (if one was given)
            split_input = [s.strip() for s in user_input.split(';')]
            individual_amounts = split_input[0]
            if len(split_input) > 1:
                comments = (';'.join(split_input[1:]))

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
                print("Invalid format.")


    return account_name, amount, comments

def handle_split(completer):
    """
    Returns a dictionary mapping accounts with associated amount, as entered
    by the user.
    """
    account_info = dict()
    next_account, amount, comments = get_account_from_user(completer)
    while next_account:
        # TODO: should we warn user here in case they messed it up?
        if not next_account in account_info:
            account_info[next_account] = (amount, comments)
        else:
            # if account was already used, add new info to the old
            old_amount, old_comments = account_info[next_account]
            account_info[next_account] = ("(" + old_amount + "+" + amount + ")",
                                          old_comments + " ; " + comments)

        next_account, amount, comments = get_account_from_user(completer)

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
    print("s : Snooze")

    while True:
        selection = input("\nEnter selection: ")
        if selection.isdigit():
            # use blank ammount (which will auto-balance) and comment for
            # pre-selection
            account_info = dict()
            selected_index = int(selection)
            if selected_index > 0 and selected_index <= len(top_accounts):
                account_info[top_accounts[selected_index-1][0]] = ('', '')
                break
            else:
                print("Invalid selection!")
        elif selection == 'o':
            account_info = handle_split(completer)
            break
        elif selection == 's':
            account_info = None
            break
        else:
            print("Invalid selection!")

    return account_info


def get_accounts(account_completer, desc, associated_accounts, match_threshold=90):
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
        if accounts is not None:
            if desc in associated_accounts:
                associated_accounts[desc].update(accounts.keys())
            else:
                associated_accounts[desc] = collections.Counter(accounts.keys())
    else:
        print("Could not find a previous transaction that is a close match.")
        print("o : Other / Split...")
        print("s : Snooze")

        valid_selection = False

        while True:
            selection = input("\nEnter selection: ")
            if selection == 'o':
                accounts = handle_split(account_completer)
                associated_accounts[desc] = collections.Counter(accounts.keys())
                break
            elif selection == 's':
                return None
            else:
                print("Invalid selection!")

    return accounts

def create_transaction(csv_entry, columns, account_completer,
                       associated_accounts):
    """ Create a transaction based on the given CSV file entry. """

    print()

    combined_debit_credit = columns['debit'] == columns['credit']

    if combined_debit_credit:
        print(" || ".join(csv_entry[i] for i in [columns['date'],
                                                 columns['desc'],
                                                 columns['debit']]))
    else:
        print(" || ".join(csv_entry[i] for i in [columns['date'],
                                                 columns['desc'],
                                                 columns['debit'],
                                                 columns['credit']]))

    transaction = dict()
    transaction['date'] = parse(csv_entry[columns['date']]).strftime("%Y-%m-%d")
    transaction['description'] = csv_entry[columns['desc']]

    # TODO: make sure there isn't a "$" in debit or credit column

    accounts = dict()
    x = get_accounts(account_completer, csv_entry[columns['desc']], associated_accounts)

    if x is None:
        """ User chose to 'snooze' processing this entry so there is no
        transaction to return now. """
        return None
    else:
        accounts.update(x)


    if not combined_debit_credit and csv_entry[columns['debit']] and csv_entry[columns['credit']]:
        raise RuntimeError("Entry has both debit and credit")

    this_account_amount = "$"
    if combined_debit_credit:
        if csv_entry[columns['debit']][0] == "-":
            # "-" with combined debit/credit implies credit, i.e.
            # positive amount for this_account
            this_account_amount += csv_entry[columns['debit']][1:]
        else:
            # lack of "-" for combined debit/credit implies debit,
            # i.e.  negative amount from this_account
            this_account_amount += "-" + csv_entry[columns['debit']]
    elif csv_entry[columns['debit']]:
        if csv_entry[columns['debit']][0] != "-":
            this_account_amount += "-"
        this_account_amount += csv_entry[columns['debit']]
    else:
        this_account_amount += csv_entry[columns['credit']]

    accounts[this_account] = (this_account_amount, '') # empty string is for blank transation comment

    transaction['accounts'] = accounts

    return transaction

def import_transactions(csv_filename, this_account):
    """
    Imports data from CSV file into database table.
    """
    with open(csv_filename, newline='') as csv_file:
        csv_has_header = csv.Sniffer().has_header(csv_file.read(1024))
        assert csv_has_header, "No header line found in CSV"
        csv_file.seek(0)

        csv_reader = csv.reader(csv_file)
        header = next(csv_reader, None)

        for i in range(len(header)):
            print(i, ":", header[i])

        columns = {}
        columns['date'] = int(input("Which entry contains the transaction date? "))
        columns['desc'] = int(input("Which entry contains the description? "))
        columns['debit'] = int(input("Which entry contains the debit amount? "))
        columns['credit'] = int(input("Which entry contains the credit amount? "))

        combined_debit_credit = columns['debit'] == columns['credit']

        target_db = TinyDB('imported.json')
        target_db.truncate() # FIXME: remove this for final version

        #source_db = TinyDB('converted.json')

        for row in csv_reader:
            print(row)

            if combined_debit_credit:
                print(" || ".join(row[i] for i in [columns['date'],
                                                         columns['desc'],
                                                         columns['debit']]))
            else:
                print(" || ".join(row[i] for i in [columns['date'],
                                                         columns['desc'],
                                                         columns['debit'],
                                                         columns['credit']]))

            transaction = dict()
            transaction['account'] = this_account
            transaction['date'] = parse(row[columns['date']]).strftime("%Y-%m-%d")

            description = row[columns['desc']]
            transaction['description'] = description

            close_matches = [name for name, score in process.extract(description,
                                                                     associated_accounts.keys())
                             if score >= match_threshold]

            payee = input("Enter Payee Name: ")
            transaction['payee'] = payee
            #print(transaction)
            target_db.insert(transaction)

        for row in target_db:
            print(row)


def read_bank_transactions(csv_filename, account_completer, this_account,
                           associated_accounts, start_date=None,
                           end_date=None):
    """
    Returns a list of transactions based on a given CSV file.
    Each transaction will include the date, a description of the transaction
    (i.e. the payee), and a dictionary mapping the accounts used by this
    transaction and the amount of money associated with that account for this
    transaction.
    """
    with open(csv_filename, newline='') as csv_file:
        csv_has_header = csv.Sniffer().has_header(csv_file.read(1024))
        if csv_has_header:
            start_index = 1
        else:
            start_index = 0

        csv_file.seek(0)

        csv_reader = csv.reader(csv_file)
        rows = []
        for row in csv_reader:
            print(row)
            rows += [row]

        for i in range(len(rows[0])):
            print(i, ":", rows[0][i])

        columns = {}
        columns['date'] = int(input("Which entry contains the transaction date? "))
        columns['desc'] = int(input("Which entry contains the description? "))
        columns['debit'] = int(input("Which entry contains the debit amount? "))
        columns['credit'] = int(input("Which entry contains the credit amount? "))



        sorted_rows = sorted(rows[start_index:],
                             key=lambda r: parse(r[columns['date']]))

        if start_date is None:
            start_date = parse("1900-01-01")
        if end_date is None:
            end_date = parse("3005-12-31")  # childish

        filtered_rows = filter(lambda r: start_date <= parse(r[columns['date']]) <= end_date, sorted_rows)

        transactions = []
        snoozed_entries = []
        for entry in filtered_rows:
            t = create_transaction(entry, columns, account_completer,
                                   associated_accounts)
            if t is not None:
                transactions.append(t)
            else:
                snoozed_entries.append(entry)

        while snoozed_entries:
            """ Keep looping through snoozed entries while there are any. """
            t = create_transaction(snoozed_entries[0], columns, account_completer,
                                   associated_accounts)
            if t is not None:
                transactions.append(t)
            else:
                snoozed_entries.append(snoozed_entries[0])

            del snoozed_entries[0]

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
    for acc, (amt, comm) in transaction['accounts'].items():
        s += "\t" + acc + "\t\t" + amt
        if comm:
            # add comment(s) if there are any
            s += "\t; " + comm
        s += "\n"

    s += "\n"   # blank line after transaction, muy importante
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
    parser = argparse.ArgumentParser()
    parser.add_argument("training_data", help="Ledger file used for learning.")
    parser.add_argument("csv_file", help="CSV file financial transactions.")
    parser.add_argument("output", help="File to which new entries are written.")
    parser.add_argument("--account", help="Account associated with transactions.")
    parser.add_argument("--startdate", type=parse,
                        help="All entries BEFORE this datw will be ignored")
    parser.add_argument("--enddate", type=parse,
                        help="All entries AFTER this datw will be ignored")
    args = parser.parse_args()

    if args.account:
        this_account = args.account
    else:
        this_account = input("Enter the CSV file's account name: ")

    all_accounts, assoc_accounts = read_ledger_entries(args.training_data,
                                                       this_account)

    completer = AccountCompleter(list(all_accounts))
    readline.set_completer_delims(':')
    readline.set_completer(completer.complete)
    readline.parse_and_bind('tab: complete')

    # hack for macOS?
    readline.parse_and_bind("bind -e")
    readline.parse_and_bind("bind '\t' rl_complete")

    """
    new_transactions = read_bank_transactions(args.csv_file, completer,
                                              this_account, assoc_accounts,
                                              start_date=args.startdate,
                                              end_date=args.enddate)
    """

    new_transactions = import_transactions(args.csv_file, this_account)

    """
    db = TinyDB('journal.json')
    for nt in new_transactions:
        print(nt)
        db.insert(nt)
    """

    # TODO: allow user to specify whether to append or to overwrite the output
    # file
    #write_transactions_to_file(args.output, new_transactions)
