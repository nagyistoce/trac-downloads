
def do_upgrade(env, cursor):

    query = "CREATE TABLE `download_log` ( \
             `release_id` INTEGER UNSIGNED NOT NULL, \
             `user_id` INTEGER UNSIGNED NOT NULL, \
             `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, \
              PRIMARY KEY (`release_id`,`user_id`,`timestamp`))"

    try:
        # Create table
        cursor.execute(query)

        # Set database schema version.
        cursor.execute("UPDATE system SET value = 2 WHERE name = 'downloads_version'")
    except:
        pass

