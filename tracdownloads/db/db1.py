from trac.db import Table, Column, Index, DatabaseManager

# Commont SQL statements

tables = [
  Table('download', key = 'id')[
    Column('id', type = 'integer', auto_increment = True),
    Column('file'),
    Column('description'),
    Column('size', type = 'integer'),
    Column('time', type = 'integer'),
    Column('count', type = 'integer'),
    Column('author'),
    Column('tags'),
    Column('component'),
    Column('version'),
    Column('platform', type = 'integer'),
    Column('type', type = 'integer'),
    Column('featured', type = 'tinyint')
  ],
  Table('platform', key = 'id')[
    Column('id', type = 'integer', auto_increment = True),
    Column('name'),
    Column('description')
  ],
  Table('download_type', key = 'id')[
    Column('id', type = 'integer', auto_increment = True),
    Column('name'),
    Column('description')
  ]
]

values = ["INSERT INTO platform (name) VALUES ('Series 40')",
  "INSERT INTO platform (name) VALUES ('Series 60')",
  "INSERT INTO platform (name) VALUES ('Symbian')",
  "INSERT INTO platform (name) VALUES ('Maemo')",
  "INSERT INTO platform (name) VALUES ('MeeGo')",
  "INSERT INTO platform (name) VALUES ('Windows')",
  "INSERT INTO platform (name) VALUES ('Mac OS X')",
  "INSERT INTO platform (name) VALUES ('Linux')",
  "INSERT INTO platform (name) VALUES ('Other')",
  "INSERT INTO download_type (name) VALUES ('Binary')",
  "INSERT INTO download_type (name) VALUES ('Source')",
  "INSERT INTO download_type (name) VALUES ('Data')",
  "INSERT INTO download_type (name) VALUES ('Documentation')",
  "INSERT INTO download_type (name) VALUES ('Other')",
  "INSERT INTO system (name, value) VALUES ('downloads_description', 'List of available downloads:')"
]

def do_upgrade(env, cursor):
    db_connector, _ = DatabaseManager(env)._get_connector()

    # Create tables
    for table in tables:
        for statement in db_connector.to_sql(table):
            cursor.execute(statement)

    # Insert default values
    for statement in values:
        cursor.execute(statement)

    # Set database schema version.
    cursor.execute("INSERT INTO system (name, value) VALUES ('downloads_version', '1')")
