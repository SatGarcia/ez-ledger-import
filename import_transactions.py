import csv, sys, argparse

from tinydb import TinyDB, Query
from fuzzywuzzy import process
from dateutil.parser import parse

def import_transactions(csv_filename, db_filename, this_account, match_threshold=60):
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

        source_db = TinyDB(db_filename, sort_keys=True, indent=4, separators=(',', ': '))

        imports = source_db.table('imports')
        imports.truncate() # FIXME: remove this for final version

        # TODO: make all_descriptions a dict from desc. to payee
        all_descriptions = set()
        for row in source_db:
            #if row['description'] not in all_descriptions:
            #    all_descriptions.append(row['description'])
            all_descriptions.add(row['description'])

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

            # TODO: make this an assert?
            if not combined_debit_credit and row[columns['debit']] and row[columns['credit']]:
                raise RuntimeError("Entry has both debit and credit")

            transaction = dict()
            transaction['source_file'] = csv_filename
            transaction['date'] = parse(row[columns['date']]).strftime("%Y-%m-%d")

            description = row[columns['desc']]
            transaction['description'] = description

            # TODO: add description to all_descriptions
            # Note that this will require some care with target and source
            # tables

            this_account_amount = "$"
            if combined_debit_credit:
                if row[columns['debit']][0] == "-":
                    # "-" with combined debit/credit implies credit, i.e.
                    # positive amount for this_account
                    this_account_amount += row[columns['debit']][1:]
                else:
                    # lack of "-" for combined debit/credit implies debit,
                    # i.e.  negative amount from this_account
                    this_account_amount += "-" + row[columns['debit']]

            elif row[columns['debit']]:
                if row[columns['debit']][0] != "-":
                    this_account_amount += "-"
                this_account_amount += row[columns['debit']]

            else:
                this_account_amount += row[columns['credit']]

            account_info = {'account': this_account,
                            'amount': this_account_amount}

            transaction['accounts'] = [account_info]

            close_matches = [name for name, score in process.extract(description,
                                                                     all_descriptions)
                             if score >= match_threshold]

            close_payees = list(set([source_db.get(Query().description == desc)['payee']
                                        for desc in close_matches]))

            if len(close_payees) == 0:
                # no close matches
                print("No close matches found for:", description)
                payee = input("Enter Payee Name: ")

            else:
                # print out each close match and ask user to select
                print("\nClose Matches: (Select one)")
                for i, p in enumerate(close_payees):
                    #t = source_db.get(Query().description == desc)
                    print(i+1, ":", p)

                print("0 : Other...")

                selection = int(input("\nEnter the selection: "))
                if selection == 0:
                    payee = input("Enter Payee Name: ")
                else:
                    payee = close_payees[selection - 1]

            transaction['payee'] = payee
            #print(transaction)
            imports.insert(transaction)

        for row in imports:
            print(row)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("db_file", help="TinyDB database with transactions.")
    parser.add_argument("csv_file", help="CSV file with financial transactions.")
    parser.add_argument("--account", help="Account associated with transactions.")
    """
    parser.add_argument("--startdate", type=parse,
                        help="All entries BEFORE this datw will be ignored")
    parser.add_argument("--enddate", type=parse,
                        help="All entries AFTER this datw will be ignored")
    """
    args = parser.parse_args()

    if args.account:
        this_account = args.account
    else:
        this_account = input("Enter the CSV file's account name: ")

    import_transactions(args.csv_file, args.db_file, this_account)