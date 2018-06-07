import csv, sys, re, collections

def get_string_without_comment(str):
    return re.split("(?:  | *\t+);", str)[0]

def read_bank_transactions():
    with open('test.csv', newline='') as csv_file:
        csv_has_header = csv.Sniffer().has_header(csv_file.read(1024))
        csv_file.seek(0)

        csv_reader = csv.reader(csv_file)
        for row in csv_reader:
            print(row)
            #print(', '.join(row))

def read_ledger_entries(this_account):
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

    return associated_accounts


read_bank_transactions()
assoc_accounts = read_ledger_entries("Liabilities:CapitalOne")

for k,v in assoc_accounts.items():
    print("\npayee:", k)
    print("accounts:")
    for acc in v.most_common():
        print("\t", acc[0])
