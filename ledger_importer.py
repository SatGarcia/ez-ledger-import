import csv, sys, re, collections, readline, argparse
import json, click

from tinydb import TinyDB, Query
from fuzzywuzzy import process
from account_completer import AccountCompleter
from dateutil.parser import parse
from datetime import date

def get_account_from_user(completer, tax_amount="1.0775"):
    """
    Asks user for the name of an account, adding it to our list of accounts in
    our auto completer.
    """
    account_name = input("Enter account name: ")
    account_name = account_name.strip()
    amount = ''
    comment = ''

    if account_name:
        completer.add_account(account_name)
        while True:
            user_input = input("Enter space-separated amounts. Append '*' to untaxed amounts: ")
            #individual_amounts = user_input.strip()

            # separate comment from the amounts (if one was given)
            split_input = [s.strip() for s in user_input.split(';')]
            individual_amounts = split_input[0]
            if len(split_input) > 1:
                comment = (';'.join(split_input[1:]))

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


    return account_name, amount, comment

def handle_split(completer):
    """
    Returns a list of dictionaries with account info. See get_match_selection
    for a description of these dictionaries.

    If there was an error, a blank list is returned.
    """
    selected_accounts = []
    account_name, amount, comment = get_account_from_user(completer)
    while account_name != "":
        existing_account = None
        for sa in selected_accounts:
            if sa['account'] == account_name:
                existing_account = sa
                break

        if existing_account is None:
            # first time entering this account name so create new dict
            new_account = {'account': account_name}
            if amount:
                new_account['amount'] = amount
            if comment:
                new_account['comment'] = comment
            selected_accounts.append(new_account)

        else:
            # if account was already used, add new info to the old
            if amount and ('amount' in existing_account):
                existing_account['amount'] = "(" + existing_account['amount'] + "+" + amount + ")"
            elif amount:
                # blank amount for existing implies they wanted auto-balance
                # but this goes against that so we need them to start over
                print("ERROR: Conflicting auto-balance directive for", account_name)
                return []

            if comment and ('comment' in existing_account):
                existing_account['comment'] += (" ; " + comment)
            elif comment:
                existing_account['comment'] = comment

        account_name, amount, comment = get_account_from_user(completer)

    return selected_accounts

def get_match_selection(frequencies, completer):
    """
    Returns a list of dictionaries containing account information for selected
    accounts. Each dictionary will contain at least the account name; it may
    also contain an amount and a comment. A missing amount means
    auto-balancing should be used.

    If the user selects to "snooze", a blank list will be returned.
    """

    top_accounts = frequencies.most_common(9)

    # start index at 1 for more user-friendliness
    for i, (acc, _) in enumerate(top_accounts):
        print(i+1, ":", acc)

    print("o : Other / Split...")
    print("s : Snooze")

    while True:
        selection = input("\nEnter selection: ")
        if selection.isdigit():
            # use blank ammount (which will auto-balance) and comment for
            # pre-selection
            selected_index = int(selection)
            if selected_index > 0 and selected_index <= len(top_accounts):
                account_info = {"account": top_accounts[selected_index-1][0]}
                return [account_info]
            else:
                print("Invalid selection!")
        elif selection == 'o':
            selected_accounts = handle_split(completer)
            while not selected_accounts:
                # empty list means something went wrong so let's restart the
                # splitting process
                print("WARNING: Restarting selection process")
                selected_accounts = handle_split(completer)

            return selected_accounts

        elif selection == 's':
            return []

        else:
            print("Invalid selection!")



def get_accounts(payee, target_account, account_completer, associated_accounts):
    """
    Returns list of dictionaries, one for each account associated with this
    transaction. Each dictionary will contain the account name, amount, and
    and (optional) comments.

    This also updates the list of associated accounts for payee, so we have a
    history for improving future transactions with the same or similar
    description.
    """

    payee_accounts = associated_accounts.get(payee)

    if payee_accounts is not None:
        # We have associated accounts from 1+ previous transactions for this payee

        # remove the target_account name to avoid confusion
        target_counter = payee_accounts[target_account]
        del payee_accounts[target_account]

        accounts = get_match_selection(payee_accounts, account_completer)

        if target_counter > 0:
            payee_accounts[target_account] = target_counter

    else:
        # First time we're seeing this payee so create a new counter for it
        payee_accounts = collections.Counter()
        associated_accounts[payee] = payee_accounts

        accounts = get_match_selection(payee_accounts, account_completer)


    if accounts:
        # user didn't snooze so update payee's counter for all the selected
        # accounts (this improves matching for future imports)
        for acc in accounts:
            payee_accounts[acc['account']] += 1

    return accounts

def set_accounts(transaction, account_completer, associated_accounts):
    """
    Set the accounts/amounts for this transaction.

    Return:
    boolean: True if accounts set, False otherwise
    """

    accounts = get_accounts(transaction['payee'],
                            transaction['accounts'][0]['account'],
                            account_completer, associated_accounts)

    if accounts == []:
        # User chose to skip reviewing this transaction
        return False
    else:
        transaction['accounts'] += accounts
        return True


def review_imports(db, account_completer, associated_accounts, target_payee=None,
                   start_date=None, end_date=None):
    """
    Review any unreviewed imports. Reviewing requires setting the associated
    accounts and amounts for the transaction.
    """

    imports_table = db.table('imports')

    Transaction = Query()

    search_string = (Transaction.reviewed == False)

    if start_date:
        search_string = search_string & (Transaction.date >= start_date)

    if end_date:
        search_string = search_string & (Transaction.date <= end_date)

    if target_payee:
        search_string = search_string & (Transaction.payee == target_payee)

    unreviewed_transactions = imports_table.search(search_string)

    unreviewed_transactions.sort(key=lambda t: t['date'])

    for transaction in unreviewed_transactions:
        assert transaction['reviewed'] == False

        assert len(transaction['accounts']) == 1, "Unreviewed imports should have only one account"

        print("\n" + " || ".join([
                                    transaction['date'], transaction['payee'],
                                    transaction['accounts'][0]['amount'],
                                    transaction['accounts'][0]['account'],
                                    transaction['description']
                                  ]))

        completed = set_accounts(transaction, account_completer, associated_accounts)

        if completed:
            # Accounts were updated so the review process for this import is
            # done.
            transaction['reviewed'] = True

            #print("Completed Transaction:")
            #print(json.dumps(transaction, indent=4))

            imports_table.update({'reviewed': True}, doc_ids=[transaction.doc_id])

            # TODO: add final confirmation after printing transaction info?

            db.insert(dict(transaction))


def get_frequencies(db):
    """
    Gets list of unique accounts of existing transactions and a dictionary
    that associates a payee with frequency of accounts used for that payee.

    Params:
    db (TinyDB) : The database to work with
    """
    all_accounts = set()
    associated_accounts = dict()
    #with open(ledger_filename) as ledger_file:
    for row in db:
        payee = row['payee']
        if payee not in associated_accounts:
            associated_accounts[payee] = collections.Counter()

        accounts = row['accounts']

        for account in accounts:
            account_name = account['account']
            all_accounts.add(account_name)
            associated_accounts[payee][account_name] += 1

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


@click.group()
def cli():
    pass

@cli.command()
@click.argument("db_filename")
@click.option("--count", default=10, help="Number of payees to print")
def top_payees(db_filename, count):
    """Prints out the COUNT most frequent payees for unreviewed imports in DB_FILENAME."""

    db = TinyDB(db_filename, sort_keys=True, indent=4, separators=(',', ': '))
    imports_table = db.table('imports')

    unreviewed = imports_table.search(Query().reviewed == False)
    print("Number of unreviewed:", len(unreviewed))
    c = collections.Counter([t['payee'] for t in unreviewed])

    for payee, count in c.most_common(count):
        print(f"{payee} ({count})")


@cli.command()
@click.argument("db_filename")
@click.option("--payee", help="Limit review to transactions with the given payee")
@click.option('--start-date', type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Starting date of transactions to review.")
@click.option('--end-date', type=click.DateTime(formats=["%Y-%m-%d"]),
              help="Ending date of transactions to review.")
def review(db_filename, payee, start_date, end_date):
    """
    Starts review of imported transactions in DB_FILENAME.

    DB_FILENAME is the TinyDB file with transactions.
    """

    if start_date and end_date and (start_date >= end_date):
        print("Start date must come BEFORE end date.")
        sys.exit(1)

    db = TinyDB(db_filename, sort_keys=True, indent=4, separators=(',', ': '))

    all_accounts, assoc_accounts = get_frequencies(db)

    completer = AccountCompleter(list(all_accounts))
    readline.set_completer_delims(':')
    readline.set_completer(completer.complete)
    readline.parse_and_bind('tab: complete')

    # hack for macOS?
    readline.parse_and_bind("bind -e")
    readline.parse_and_bind("bind '\t' rl_complete")

    if start_date:
        start_date = str(start_date.date())
    if end_date:
        end_date = str(end_date.date())

    review_imports(db, completer, assoc_accounts,
                   target_payee=payee,
                   start_date=start_date, end_date=end_date)

    # TODO: allow user to specify whether to append or to overwrite the output
    # file
    #write_transactions_to_file(args.output, new_transactions)

if __name__ == "__main__":
    cli()
