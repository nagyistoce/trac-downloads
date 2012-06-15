# -*- coding: utf-8 -*-

# Standard imports.
import os, shutil, unicodedata
from datetime import datetime

# Trac imports
from trac.core import Component, Interface, ExtensionPoint, TracError
from trac.config import Option, IntOption, BoolOption, ListOption
from trac.resource import Resource
from trac.mimeview import Mimeview
from trac.web.chrome import add_stylesheet, add_script
from trac.util.datefmt import to_timestamp, utc, format_datetime
from trac.util.text import to_unicode
from trac.web.api import RequestDone

#cqde imports
from multiproject.core.configuration import conf
from multiproject.core.db import safe_int


class IDownloadChangeListener(Interface):
    """Extension point interface for components that require notification
    when downloads are created, modified, or deleted."""

    def download_created(context, download): #@NoSelf
        """Called when a download is created. Only argument `download` is
        a dictionary with download field values."""

    def download_changed(context, download, old_download): #@NoSelf
        """Called when a download is modified.
        `old_download` is a dictionary containing the previous values of the
        fields and `download` is a dictionary with new values. """

    def download_deleted(context, download): #@NoSelf
        """Called when a download is deleted. `download` argument is
        a dictionary with values of fields of just deleted download."""

class IDownloadListener(Interface):
    def downloaded(context, download): #@NoSelf
        """Called when a file is downloaded
        """

class HelperContext():
    """ Simple database context holder
    """
    def __init__(self, cursor):
        self.cursor = cursor

class DownloadsApi(Component):

    # Download change listeners.
    change_listeners = ExtensionPoint(IDownloadChangeListener)
    download_listeners = ExtensionPoint(IDownloadListener)

    download_sort_options  = ('id', 'file','description', 'size', 'time', 'count', 'author', 'tags', 'component', 'version', 'platform', 'type')
    platform_sort_options = ('id', 'name', 'description')
    type_sort_options = ('id', 'name', 'description')

    # Configuration options.
    title = Option('downloads', 'title', 'Downloads', doc = 'Main navigation bar button title.')
    ext = ListOption('downloads', 'ext', 'zip,gz,bz2,rar',
                      doc = 'List of file extensions allowed to upload.')
    max_size = IntOption('downloads', 'max_size', 268697600,
                          'Maximum allowed file size (in bytes) for downloads. Default is 256 MB.')
    visible_fields = ListOption('downloads', 'visible_fields',
                                 'id,file,description,size,time,count,author,tags,component,version,platform,type',
                                 doc = 'List of downloads table fields that should be visible to users on Downloads section.')
    download_sort = Option('downloads', 'download_sort', 'time',
                            'Column by which downloads list will be sorted. Possible values are: %s. Default value is: time.' % ','.join(download_sort_options))
    download_sort_direction = Option('downloads', 'download_sort_direction', 'desc',
                                      'Direction of downloads list sorting. Possible values are: asc, desc. Default value is: desc.')
    platform_sort = Option('downloads', 'platform_sort', 'name',
                            'Column by which platforms list will be sorted. Possible values are: %s. Default value is: name.' % ','.join(platform_sort_options))
    platform_sort_direction = Option('downloads', 'platform_sort_direction', 'asc',
                                      'Direction of platforms list sorting. Possible values are: asc, desc. Default value is: asc.')
    type_sort = Option('downloads', 'type_sort', 'name', 'Column by which types'
                        ' list will be sorted. Possible values are: %s. Default value is: name.' % ','.join(type_sort_options))
    type_sort_direction = Option('downloads', 'type_sort_direction', 'asc',
                                  'Direction of types list sorting. Possible values are: asc, desc. Default value is: asc.')
    unique_filename = BoolOption('downloads', 'unique_filename', False,
                                  doc = 'If enabled checks if uploaded file has unique name.')

    def __init__(self):
        self.path = conf.getEnvironmentDownloadsPath(self.env)

    # Get list functions.
    def _get_items(self, context, table, columns, where = '', values = (), order_by = '', desc = False):
        # IMPORTANT: Check parameter validity to prevent possible vulnerability
        if (order_by and order_by not in self.download_sort_options
            and order_by not in self.platform_sort_options
            and order_by not in self.type_sort_options):
            self.log.warning('Invalid sort option: %s' % order_by)
            return []

        sql = 'SELECT ' + ', '.join(columns) + ' FROM ' + table + (where
          and (' WHERE ' + where) or '') + (order_by and (' ORDER BY ' +
          order_by + (' ASC', ' DESC')[bool(desc)]) or '')
        self.log.debug("%s, %s", sql, values)
        items = []
        try:
            context.cursor.execute(sql, values)
            for row in context.cursor:
                row = dict(zip(columns, row))
                items.append(row)
        except:
            self.log.exception("Cannot get items. query= %s", sql)
        return items

    def get_versions(self, context, order_by = 'name', desc = False):
        # Get versions from table.
        versions = self._get_items(context, 'version', ('name', 'description'), order_by = order_by, desc = desc)
        # Add IDs to versions according to selected sorting.
        id = 0
        for version in versions:
            id = id + 1
            version['id'] = id
        return versions

    def get_components(self, context, order_by = 'name', desc = False):
        # Get components from table.
        components = self._get_items(context, 'component', ('name', 'description'), order_by = order_by, desc = desc)
        # Add IDs to versions according to selected sorting.
        id = 0
        for component in components:
            id = id + 1
            component['id'] = id
        return components

    def get_downloads(self, context, order_by = 'id', desc = False):
        # Get downloads from table.
        downloads = self._get_items(context, 'download',
                                    ('id', 'file', 'description', 'size', 'time', 'count', 'author',
                                     'tags', 'component', 'version', 'platform', 'type', 'featured'),
                                     order_by = order_by, desc = desc)
        # Replace field IDs with apropriate objects.
        for download in downloads:
            download['platform'] = self.get_platform(context, download['platform'])
            download['type'] = self.get_type(context, download['type'])
        return downloads

    def get_featured_downloads(self, context, order_by = 'id', desc = False):
        # Get downloads from table.
        downloads = self._get_items(context, 'download',
                                    ('id', 'file', 'description', 'size', 'time', 'count', 'author',
                                     'tags', 'component', 'version', 'platform', 'type'),
                                     "featured = 1",
                                     order_by = order_by, desc = desc)
        # Replace field IDs with apropriate objects.
        for download in downloads:
            download['platform'] = self.get_platform(context, download['platform'])
            download['type'] = self.get_type(context, download['type'])
        return downloads

    def get_new_downloads(self, context, start, stop, order_by = 'time', desc = False):
        return self._get_items(context, 'download',
                               ('id', 'file', 'description', 'size', 'time', 'count', 'author',
                                'tags', 'component', 'version', 'platform', 'type', 'featured'),
                                'time BETWEEN %s AND %s', (start, stop), order_by = order_by, desc = desc)

    def get_platforms(self, context, order_by = 'id', desc = False):
        return self._get_items(context, 'platform', ('id', 'name',
          'description'), order_by = order_by, desc = desc)

    def get_types(self, context, order_by = 'id', desc = False):
        return self._get_items(context, 'download_type', ('id', 'name',
          'description'), order_by = order_by, desc = desc)

    # Get one item functions.
    def _get_item(self, context, table, columns, where = '', values = ()):
        sql = 'SELECT ' + ', '.join(columns) + ' FROM ' + table + (where and (' WHERE ' + where) or '')
        self.log.debug("%s, %s", sql, values)
        try:
            context.cursor.execute(sql, values)
            for row in context.cursor:
                row = dict(zip(columns, row))
                return row
        except:
            self.log.exception("Cannot get item. query = %s, values = %s", sql, values)
        return None

    def get_download(self, context, id):
        return self._get_item(context, 'download',
                              ('id', 'file', 'description', 'size', 'time', 'count', 'author',
                               'tags', 'component', 'version', 'platform', 'type', 'featured'),
                               'id = %s', (id,))

    def get_download_by_time(self, context, time):
        return self._get_item(context, 'download',
                              ('id', 'file', 'description', 'size', 'time', 'count', 'author',
                               'tags', 'component', 'version', 'platform', 'type', 'featured'),
                               'time = %s', (time,))

    def get_download_by_file(self, context, file):
        return self._get_item(context, 'download',
                              ('id', 'file', 'description', 'size', 'time', 'count', 'author',
                               'tags', 'component', 'version', 'platform', 'type', 'featured'),
                               'file = %s', (file,))

    def get_platform(self, context, id):
        platform = self._get_item(context, 'platform', ('id', 'name', 'description'), 'id = %s', (id,))
        if not platform:
            platform = {'id' : 0, 'name' : '', 'description' : ''}
        return platform

    def get_platform_by_name(self, context, name):
        platform = self._get_item(context, 'platform', ('id', 'name', 'description'), 'name = %s', (name,))
        if not platform:
            platform = {'id' : 0, 'name' : '', 'description' : ''}
        return platform

    def get_type(self, context, id):
        type = self._get_item(context, 'download_type', ('id', 'name', 'description'), 'id = %s', (id,))
        if not type:
            type = {'id' : 0, 'name' : '', 'description' : ''}
        return type

    def get_type_by_name(self, context, name):
        type = self._get_item(context, 'download_type', ('id', 'name', 'description'), 'name = %s', (name,))
        if not type:
            type = {'id' : 0, 'name' : '', 'description' : ''}
        return type

    def get_description(self, context):
        sql = "SELECT value FROM system WHERE name = 'downloads_description'"
        self.log.debug(sql)
        context.cursor.execute(sql)
        for row in context.cursor:
            return row[0]

    def get_summary_items(self):
        featured = []

        # Get database access.
        db = self.env.get_db_cnx()
        cursor = db.cursor()

        # Create context
        context = HelperContext(cursor)

        # Get downloads from table.
        downloads = self._get_items(context, 'download', ('id', 'file', 'platform'), "featured = 1",
                                     order_by = 'id', desc = False)
        # Replace field IDs with apropriate objects and add downloads.
        for download in downloads:
            platform = self.get_platform(context, download['platform'])
            path = conf.getEnvironmentDownloadsUrl(self.env, to_unicode(download['id']))
            self.log.debug('Download url is %s' % (path,))
            if len(download['file']) > 28:
                title = download['file'][0:28] + "..."
            else:
                title = download['file']
            featured.append({ 'platform': platform['name'], 'url': path, 'title': title, 'origtitle': download['file']})
        cursor.close()
        db.close()
        return featured

    def clean_featured(self, context):
        sql = "UPDATE download SET featured = 0 WHERE featured = 1"
        self.log.debug(sql)
        context.cursor.execute(sql)

    def edit_featured(self, context, download_ids):
        try:
            sql = "UPDATE download SET featured = 1 WHERE id IN (" + \
             ', '.join([to_unicode(safe_int(download_id)) for download_id in download_ids]) + ')'
            self.log.debug(sql)
            context.cursor.execute(sql)
        except:
            self.log.exception("Downloads featured operation failed, query was %s ", sql)

    # Add item functions.
    def _add_item(self, context, table, item):
        fields = item.keys()
        values = item.values()
        sql = "INSERT INTO %s (" % (table,) + ", ".join(fields) + ") VALUES (" \
          + ", ".join(["%s" for I in xrange(len(fields))]) + ")"
        self.log.debug("%s, %s" % (sql, tuple(values)))
        try:
            context.cursor.execute(sql, tuple(values))
        except:
            self.log.exception("Downloads add operation failed, query was %s, values %s", sql, values)

    def add_download(self, context, download):
        self._add_item(context, 'download', download)

    def add_platform(self, context, platform):
        self._add_item(context, 'platform', platform)

    def add_type(self, context, type):
        self._add_item(context, 'download_type', type)

    # Edit item functions.

    def _edit_item(self, context, table, id, item):
        fields = item.keys()
        values = item.values()
        sql = "UPDATE %s SET " % (table,) + ", ".join([("%s = %%s" % (field))
          for field in fields]) + " WHERE id = %s"
        self.log.debug("%s, %s", sql, tuple(values + [id]))
        context.cursor.execute(sql, tuple(values + [id]))

    def edit_download(self, context, id, download):
        self._edit_item(context, 'download', id, download)

    def edit_platform(self, context, id, platform):
        self._edit_item(context, 'platform', id, platform)

    def edit_type(self, context, id, type):
        self._edit_item(context, 'download_type', id, type)

    def edit_description(self, context, description):
        sql = "UPDATE system SET value = %s WHERE name = 'downloads_description'"
        self.log.debug("%s, %s", sql, description)
        context.cursor.execute(sql, (description,))

    # Delete item functions.
    def _delete_item(self, context, table, id):
        sql = "DELETE FROM " + table + " WHERE id = %s"
        self.log.debug("%s, %s", sql, id)
        context.cursor.execute(sql, (id,))

    def _delete_item_ref(self, context, table, column, id):
        sql = "UPDATE " + table + " SET " + column + " = NULL WHERE " + column + " = %s"
        self.log.debug("%s, %s", sql, id)
        context.cursor.execute(sql, (id,))

    def delete_download(self, context, id):
        self._delete_item(context, 'download', id)

    def delete_platform(self, context, id):
        self._delete_item(context, 'platform', id)
        self._delete_item_ref(context, 'download', 'platform', id)

    def delete_type(self, context, id):
        self._delete_item(context, 'download_type', id)
        self._delete_item_ref(context, 'download', 'type', id)

    # Misc database access functions.

    def _get_attribute(self, context, table, column, where = '', values = ()):
        sql = 'SELECT ' + column + ' FROM ' + table + (where and (' WHERE ' +
          where) or '')
        self.log.debug("%s, %s", sql, values)
        context.cursor.execute(sql, values)
        for row in context.cursor:
            return row[0]
        return None

    def get_download_id_from_file(self, context, file):
        return self._get_attribute(context, 'download', 'id', 'file = %s',
          (file,))

    def get_number_of_downloads(self, context, download_ids = None):
        sql = 'SELECT SUM(count) FROM download' + (download_ids and
          (' WHERE id in (' + ', '.join([to_unicode(safe_int(download_id)) for download_id
          in download_ids]) + ')') or '')
        self.log.debug(sql)
        context.cursor.execute(sql)
        for row in context.cursor:
            return row[0]
        return None

    # Proces request functions.
    def process_downloads(self, context):
        # Clear data for next request.
        req_data = {}

        # Get database access.
        db = self.env.get_db_cnx()
        context.cursor = db.cursor()

        # Get request mode
        modes = self._get_modes(context)
        self.log.debug('modes: %s' % modes)

        # Perform mode actions
        self._do_actions(context, modes, req_data)

        # Fill up the template data.
        req_data['authname'] = context.req.authname
        req_data['time'] = format_datetime(datetime.now(utc))
        req_data['realm'] = context.resource.realm

        # Add CSS styles
        add_stylesheet(context.req, 'common/css/wiki.css')
        add_stylesheet(context.req, 'downloads/css/downloads.css')
        add_stylesheet(context.req, 'downloads/css/admin.css')

        # Add JavaScripts
        add_script(context.req, 'common/js/trac.js')
        add_script(context.req, 'common/js/wikitoolbar.js')

        # Commit database changes and return template and data.
        db.commit()
        return modes[-1] + '.html', {'downloads' : req_data}

    # Internal functions.

    def _get_modes(self, context):
        # Get request arguments.
        page = context.req.args.get('page')
        action = context.req.args.get('action')
        self.log.debug('context: %s page: %s action: %s' % (context, page, action))

        # Determine mode.
        if context.resource.realm == 'downloads-admin':
            if page == 'downloads':
                if not self._is_post(context):
                    return ['admin-downloads-list']
                if action == 'post-add':
                    return ['downloads-post-add', 'admin-downloads-list']
                elif action == 'post-edit':
                    return ['downloads-post-edit', 'admin-downloads-list']
                elif action == 'delete':
                    return ['downloads-delete', 'admin-downloads-list']
                elif action == 'multiaction':
                    selected_action = context.req.args.get('actionselector')
                    if selected_action == 'delete':
                        return ['downloads-delete', 'admin-downloads-list']
                    elif selected_action == 'featured':
                        return ['downloads-featured', 'admin-downloads-list']
                    else:
                        return ['admin-downloads-list']
                else:
                    return ['admin-downloads-list']
            elif page == 'platforms':
                if not self._is_post(context):
                    return ['admin-platforms-list']
                if action == 'post-add':
                    return ['platforms-post-add', 'admin-platforms-list']
                elif action == 'post-edit':
                    return ['platforms-post-edit', 'admin-platforms-list']
                elif action == 'delete':
                    return ['platforms-delete', 'admin-platforms-list']
                else:
                    return ['admin-platforms-list']
            elif page == 'types':
                if not self._is_post(context):
                    return ['admin-types-list']
                if action == 'post-add':
                    return ['types-post-add', 'admin-types-list']
                elif action == 'post-edit':
                    return ['types-post-edit', 'admin-types-list']
                elif action == 'delete':
                    return ['types-delete', 'admin-types-list']
                else:
                    return ['admin-types-list']
        elif context.resource.realm == 'downloads-core':
            if action == 'get-file':
                return ['get-file']
        elif context.resource.realm == 'downloads-downloads':
            if not self._is_post(context):
                return ['downloads-list']
            if action == 'post-add':
                return ['downloads-post-add', 'downloads-list']
            elif action == 'edit':
                return ['description-edit', 'downloads-list']
            elif action == 'post-edit':
                return ['description-post-edit', 'downloads-list']
            else:
                return ['downloads-list']
        else:
            pass

    def _is_post(self, context):
        return context.req.method == 'POST'

    def _do_actions(self, context, actions, req_data):
        for action in actions:
            if action == 'get-file':
                context.req.perm.require('DOWNLOADS_VIEW')

                # Get request arguments.
                download_id = context.req.args.get('id') or 0
                download_file = context.req.args.get('file')

                # Get download.
                if download_id:
                    download = self.get_download(context, download_id)
                else:
                    download = self.get_download_by_file(context, download_file)

                # Check if requested download exists.
                if not download:
                    raise TracError('File not found.')

                # Check resource based permission.
                context.req.perm.require('DOWNLOADS_VIEW', Resource('downloads', download['id']))

                filename = os.path.basename(download['file'])
                # Get download file path.
                path = os.path.normpath(os.path.join(self.path, to_unicode(download['id']), filename))
                self.log.debug('path: %s' % (path,))

                # Increase downloads count.
                new_download = {'count' : download['count'] + 1}

                # Edit download.
                self.edit_download(context, download['id'], new_download)

                # Notify change listeners.
                for listener in self.change_listeners:
                    listener.download_changed(context, new_download,
                      download)

                # Commit DB before file send.
                db = self.env.get_db_cnx()
                db.commit()

                # Guess mime type.
                file = open(path.encode('utf-8'), "r")
                file_data = file.read(1000)
                file.close()
                mimeview = Mimeview(self.env)
                mime_type = mimeview.get_mimetype(path, file_data)
                if not mime_type:
                    mime_type = 'application/octet-stream'
                if 'charset=' not in mime_type:
                    charset = mimeview.get_charset(file_data, mime_type)
                    mime_type = mime_type + '; charset=' + charset

                # Return uploaded file to request.
                context.req.send_header('Content-Disposition', 'attachment;filename="%s"' % (os.path.normpath(download['file'])))
                context.req.send_header('Content-Description', download['description'])
                try:
                    context.req.send_file(path.encode('utf-8'), mime_type)
                except RequestDone:
                    try:
                        for listener in self.download_listeners:
                            listener.downloaded(context, download)
                    finally:
                        raise RequestDone

            elif action == 'downloads-list':
                context.req.perm.require('DOWNLOADS_VIEW')

                # Get form values.
                order = context.req.args.get('order') or self.download_sort
                if context.req.args.has_key('desc'):
                    desc = context.req.args.get('desc') == '1'
                else:
                    desc = self.download_sort_direction

                req_data['order'] = order
                req_data['desc'] = desc
                req_data['has_tags'] = self.env.is_component_enabled('tractags.api.TagEngine')
                req_data['visible_fields'] = self.visible_fields
                req_data['title'] = self.title
                req_data['description'] = self.get_description(context)
                req_data['downloads'] = self.get_downloads(context, order, desc)
                req_data['visible_fields'] = [visible_field for visible_field
                  in self.visible_fields]

                # Component, versions, etc. are needed only for new download
                # add form.
                if context.req.perm.has_permission('DOWNLOADS_ADD'):
                    req_data['components'] = self.get_components(context)
                    req_data['versions'] = self.get_versions(context)
                    req_data['platforms'] = self.get_platforms(context)
                    req_data['types'] = self.get_types(context)

            elif action == 'admin-downloads-list':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get form values
                order = context.req.args.get('order') or self.download_sort
                if context.req.args.has_key('desc'):
                    desc = context.req.args.get('desc') == '1'
                else:
                    desc = self.download_sort_direction
                download_id = safe_int(context.req.args.get('download', '0'))

                req_data['supported_files'] = ', '.join(self.ext)
                req_data['order'] = order
                req_data['desc'] = desc
                req_data['has_tags'] = self.env.is_component_enabled('tractags.api.TagEngine')
                req_data['download'] = self.get_download(context, download_id)
                req_data['downloads'] = self.get_downloads(context, order, desc)
                req_data['components'] = self.get_components(context)
                req_data['versions'] = self.get_versions(context)
                req_data['platforms'] = self.get_platforms(context)
                req_data['types'] = self.get_types(context)

                if not req_data['components']:
                    req_data['cstate'] = {'disabled': 'disabled'}
                if not req_data['versions']:
                    req_data['vstate'] = {'disabled': 'disabled'}
                if not req_data['platforms']:
                    req_data['pstate'] = {'disabled': 'disabled'}
                if not req_data['types']:
                    req_data['tstate'] = {'disabled': 'disabled'}
            elif action == 'description-edit':
                context.req.perm.require('DOWNLOADS_ADMIN')

            elif action == 'description-post-edit':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get form values.
                description = context.req.args.get('description')

                # Set new description.
                self.edit_description(context, description)

            elif action == 'downloads-post-add':
                context.req.perm.require('DOWNLOADS_ADD')

                # Get form values.
                file, filename, file_size = self._get_file_from_req(context)
                download = {'file' : filename,
                            'description' : context.req.args.get('description'),
                            'size' : file_size,
                            'time' : to_timestamp(datetime.now(utc)),
                            'count' : 0,
                            'author' : context.req.authname,
                            'tags' : context.req.args.get('tags'),
                            'component' : context.req.args.get('component'),
                            'version' : context.req.args.get('version'),
                            'platform' : context.req.args.get('platform'),
                            'type' : context.req.args.get('type')}

                # Upload file to DB and file storage.
                self._add_download(context, download, file)

                # Close input file.
                file.close()

            elif action == 'downloads-post-edit':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get form values.
                download_id = safe_int(context.req.args.get('id'))
                old_download = self.get_download(context, download_id)
                download = {'description' : context.req.args.get('description'),
                            'tags' : context.req.args.get('tags'),
                            'component' : context.req.args.get('component'),
                            'version' : context.req.args.get('version'),
                            'platform' : context.req.args.get('platform'),
                            'type' : context.req.args.get('type')}

                try:
                    # NOTE: if only description changed, file cannot be found and this raises TracError
                    file, filename, file_size = self._get_file_from_req(context)

                    if old_download['file'] != filename or old_download['size'] != file_size:
                        download['file'] = filename
                        download['size'] = file_size
                        download['author'] = context.req.authname
                        download['time'] = to_timestamp(datetime.now(utc))
                        self._add_download(context, download, file, {'id': download_id, 'file': old_download['file']})
                    else:
                        # Edit Download.
                        self.edit_download(context, download_id, download)

                except:
                    # Edit Download.
                    self.edit_download(context, download_id, download)

                finally:
                    # Close input file.
                    if 'file' in locals():
                        file.close()

                # Notify change listeners.
                for listener in self.change_listeners:
                    listener.download_changed(context, download, old_download)
            elif action == 'downloads-featured':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get selected downloads.
                selection = context.req.args.get('selection')
                if isinstance(selection, (str, unicode)):
                    selection = [selection]
                if selection:
                    self.clean_featured(context)
                    self.edit_featured(context, selection)
            elif action == 'downloads-delete':
                context.req.perm.require('DOWNLOADS_ADMIN')
                # Get selected downloads.
                selection = context.req.args.get('selection')
                if isinstance(selection, (str, unicode)):
                    selection = [selection]
                # Delete download.
                if selection:
                    for download_id in selection:
                        download_id = safe_int(download_id)
                        download = self.get_download(context, download_id)
                        self.log.debug('download: %s' % (download,))
                        self._delete_download(context, download)

            elif action == 'admin-platforms-list':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get form values.
                order = context.req.args.get('order') or self.platform_sort
                if context.req.args.has_key('desc'):
                    desc = context.req.args.get('desc') == '1'
                else:
                    desc = self.platform_sort_direction
                platform_id = safe_int(context.req.args.get('platform','0'))

                if order not in self.platform_sort_options:
                    raise TracError('Invalid sort order')

                # Display platforms.
                req_data['order'] = order
                req_data['desc'] = desc
                req_data['platform'] = self.get_platform(context,
                  platform_id)
                req_data['platforms'] = self.get_platforms(context, order,
                  desc)

            elif action == 'platforms-post-add':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get form values.
                platform = {'name' : context.req.args.get('name'),
                            'description' : context.req.args.get('description')}

                # Add platform.
                self.add_platform(context, platform)

            elif action == 'platforms-post-edit':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get form values.
                platform_id = context.req.args.get('id')
                platform = {'name' : context.req.args.get('name'),
                            'description' : context.req.args.get('description')}

                # Add platform.
                self.edit_platform(context, platform_id, platform)

            elif action == 'platforms-delete':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get selected platforms.
                selection = context.req.args.get('selection')
                if isinstance(selection, (str, unicode)):
                    selection = [selection]

                # Delete platforms.
                if selection:
                    for platform_id in selection:
                        platform_id = safe_int(platform_id)
                        self.delete_platform(context, platform_id)

            elif action == 'admin-types-list':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get form values
                order = context.req.args.get('order') or self.type_sort
                if order not in self.type_sort_options:
                    self.log.debug('Invalid order option: %s' % order)
                    order = self.type_sort

                if context.req.args.has_key('desc'):
                    desc = context.req.args.get('desc') == '1'
                else:
                    desc = self.type_sort_direction
                platform_id = safe_int(context.req.args.get('type','0'))

                # Display platforms.
                req_data['order'] = order
                req_data['desc'] = desc
                req_data['type'] = self.get_type(context, platform_id)
                req_data['types'] = self.get_types(context, order, desc)

            elif action == 'types-post-add':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get form values.
                type = {'name' : context.req.args.get('name'),
                        'description' : context.req.args.get('description')}

                # Add type.
                self.add_type(context, type)

            elif action == 'types-post-edit':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get form values.
                type_id = safe_int(context.req.args.get('id'))
                type = {'name' : context.req.args.get('name'),
                        'description' : context.req.args.get('description')}

                # Add platform.
                self.edit_type(context, type_id, type)

            elif action == 'types-delete':
                context.req.perm.require('DOWNLOADS_ADMIN')

                # Get selected types.
                selection = context.req.args.get('selection')
                if isinstance(selection, (str, unicode)):
                    selection = [selection]

                # Delete types.
                if selection:
                    for type_id in selection:
                        type_id = safe_int(type_id)
                        self.delete_type(context, type_id)

    def _add_download(self, context, download, file, old_download = None):
        """
        Full implementation of download addition. It creates DB entry for
        download <download> and stores download file <file> to file system.
        """
        # Check for file name uniqueness.
        if self.unique_filename:
            if self.get_download_by_file(context, download['file']):
                raise TracError('File with same name is already uploaded and'
                  ' unique file names are enabled.')

        # Check correct file type.
        name, ext = os.path.splitext(download['file'])
        if not 'all' in self.ext:
            self.log.debug('file: %s file_ext: %s ext: %s' % (name, ext, self.ext))
            if not ext[1:].lower() in self.ext:
                raise TracError('Unsupported file type.')

        # Check for maximum file size.
        if self.max_size >= 0 and download['size'] > self.max_size:
            raise TracError('Maximum file size: %s bytes' % (self.max_size), 'Upload failed')

        if old_download:
            # Edit Download.
            self.edit_download(context, old_download['id'], download)
        else:
            # Add new download to DB.
            self.add_download(context, download)

        # Get inserted download by time to get its ID.
        download = self.get_download_by_time(context, download['time'])

        # Prepare file paths.
        path = os.path.normpath(os.path.join(self.path, to_unicode(download['id'])))
        filepath = os.path.normpath(os.path.join(path, download['file']))

        # Remove old file, if exists
        if old_download:
            old_filename = None
            try:
                old_filename = os.path.basename(old_download['file'])
                filepathold = os.path.normpath(os.path.join(path, old_filename))
                os.remove(filepathold.encode('utf-8'))
            except Exception, error:
                self.log.exception("Error deleting old file %s, filename was '%s'",
                    old_download['id'], old_filename)

        # Store uploaded image.
        try:
            if not os.path.exists(path):
                os.makedirs(path.encode('utf-8'))
            out_file = open(filepath.encode('utf-8'), "wb+")
            file.seek(0)
            shutil.copyfileobj(file, out_file)
            out_file.close()
        except Exception, error:
            self.delete_download(context, download['id'])
            self.log.exception("Error storing file %s, %s", download['id'], download['name'])
            try:
                os.remove(filepath.encode('utf-8'))
            except:
                pass
            try:
                os.rmdir(path.encode('utf-8'))
            except:
                pass
            raise TracError('Error storing file %s! Are downloads activated in project?' % (download['file'],))

        if not old_download:
            # Notify change listeners.
            for listener in self.change_listeners:
                listener.download_created(context, download)

    def _delete_download(self, context, download):
        filename = None
        try:
            self.delete_download(context, download['id'])
            path = os.path.join(self.path, to_unicode(safe_int(download['id'])))
            filename = os.path.basename(download['file'])
            filepath = os.path.join(path, filename)
            path = os.path.normpath(path)
            filepath = os.path.normpath(filepath)
            os.remove(filepath)
            os.rmdir(path)

            # Notify change listeners.
            for listener in self.change_listeners:
                listener.download_deleted(context, download)
        except:
            self.log.exception("DownloadsPlugin: Cannot delete download %s, name: '%s'", download['id'], filename)

    def _get_file_from_req(self, context):
        file = context.req.args['file']

        # Test if file is uploaded.
        if not hasattr(file, 'filename') or not file.filename:
            raise TracError('No file uploaded.')

        # Get file size.
        if hasattr(file.file, 'fileno'):
            size = os.fstat(file.file.fileno())[6]
        else:
            # Seek to end of file to get its size.
            file.file.seek(0, 2)
            size = file.file.tell()
            file.file.seek(0)
        if size == 0:
            raise TracError('Can\'t upload empty file.')

        # Try to normalize the filename to unicode NFC if we can.
        # Files uploaded from OS X might be in NFD.
        self.log.debug('input filename: %s', (file.filename,))
        filename = unicodedata.normalize('NFC', to_unicode(file.filename, 'utf-8'))
        filename = os.path.basename(filename)
        self.log.debug('output filename: %s', (filename,))

        return file.file, filename, size
