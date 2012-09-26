# -*- coding: utf8 -*-

from trac.core import Component, implements, TracError
from trac.env import IEnvironmentSetupParticipant


# Last screenshots database shcema version
last_db_version = 2

class DownloadsInit(Component):
    """
       Init component initialises database and environment for downloads
       plugin.
    """
    implements(IEnvironmentSetupParticipant)

    # IEnvironmentSetupParticipanttr
    def environment_created(self):
        db = self.env.get_db_cnx()
        self.upgrade_environment(db)
        db.close()

    def environment_needs_upgrade(self, db):
        cursor = db.cursor()
        # Is database up to date?
        return self._get_db_version(cursor) != last_db_version

    def upgrade_environment(self, db):
        self.log.debug("Upgrading download plugin environment")
        cursor = db.cursor()
        # Get current database schema version
        db_version = self._get_db_version(cursor)
        # Perform incremental upgrades
        try:
            for I in range(db_version + 1, last_db_version + 1):
                script_name = 'db%i' % (I)
                module = __import__('tracdownloads.db.%s' % (script_name),
                globals(), locals(), ['do_upgrade'])
                module.do_upgrade(self.env, cursor)
                db.commit()
        except:
            raise TracError("Upgrading download plugin environment failed")
        finally:
            cursor.close()

    def _get_db_version(self, cursor):
        try:
            sql = "SELECT value FROM system WHERE name='downloads_version'"
            self.log.debug(sql)
            cursor.execute(sql)
            for row in cursor:
                return int(row[0])
            return 0
        except:
            return 0
