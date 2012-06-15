# -*- coding: utf-8 -*-

import re

from trac.core import Component, implements
from trac.config import ListOption
from trac.mimeview import Context
from trac.resource import Resource
from trac.util.html import html
from trac.web.chrome import Chrome
from trac.util.text import to_unicode, pretty_size
from trac.wiki import IWikiSyntaxProvider, IWikiMacroProvider
from trac.wiki.formatter import system_message

from api import DownloadsApi

class DownloadsWiki(Component):
    """
        The wiki module implements macro for downloads referencing.
    """
    implements(IWikiSyntaxProvider, IWikiMacroProvider)

    all_fields = [ 'id', 'file', 'description', 'size', 'time', 'count', 'author', 'tags', 'component', 'version', 'platform', 'type' ]

    # Macros documentation.
    downloads_count_macro_doc = """Display count of dowloads."""
    list_downloads_macro_doc = """Display list of download files."""
    featured_downloads_macro_doc = """Display list of featured files."""
    custom_list_downloads_macro_doc = """Display list of download files with selected columns.\n\nPossible fields: %s """ % ",".join(all_fields)
    custom_featured_downloads_macro_doc = """Display list of featured files with selected columns.\n\nPossible fields: %s """ % ",".join(all_fields)

    # Configuration options
    visible_fields = ListOption('downloads', 'visible_fields', ','.join(all_fields),
      doc = 'List of downloads table fields that should be visible to users on downloads section.')

    # IWikiSyntaxProvider
    def get_link_resolvers(self):
        yield ('download', self._download_link)

    def get_wiki_syntax(self):
        return []

    # IWikiMacroProvider

    def get_macros(self):
        yield 'DownloadsCount'
        yield 'ListDownloads'
        yield 'FeaturedDownloads'
        yield 'ListFeaturedDownloads'
        yield 'CustomListDownloads'
        yield 'CustomFeaturedDownloads'
        yield 'CustomListFeaturedDownloads'

    def get_macro_description(self, name):
        if name == 'DownloadsCount':
            return self.downloads_count_macro_doc
        if name == 'ListDownloads':
            return self.list_downloads_macro_doc
        if name == 'FeaturedDownloads' or name == 'ListFeaturedDownloads':
            return self.featured_downloads_macro_doc
        if name == 'CustomListDownloads':
            return self.custom_list_downloads_macro_doc
        if name == 'CustomFeaturedDownloads' or name == 'CustomListFeaturedDownloads':
            return self.custom_featured_downloads_macro_doc

    def expand_macro(self, formatter, name, content):
        if name == 'DownloadsCount':
            # Create request context.
            context = Context.from_request(formatter.req)('downloads-wiki')

            # Get database access.
            db = self.env.get_db_cnx()
            context.cursor = db.cursor()

            # Get API component.
            api = self.env[DownloadsApi]

            # Check empty macro content.
            download_ids = []
            if content and content.strip() != '':
                # Get download IDs or filenames from content.
                items = [item.strip() for item in content.split(',')]

                # Resolve filenames to IDs.
                for item in items:
                    try:
                        # Try if it's download ID first.
                        download_id = int(item)
                        if download_id:
                            download_ids.append(download_id)
                        else:
                            # Any zero ID means all downloads.
                            download_ids = []
                            break;
                    except ValueError:
                        # If it wasn't ID resolve filename.
                        download_id = api.get_download_id_from_file(context,
                          item)
                        if download_id:
                            download_ids.append(download_id)
                        else:
                            self.log.debug('Could not resolve download filename to ID.')

            # Empty list mean all.
            if len(download_ids) == 0:
                download_ids = None

            # Ask for aggregated downloads count.
            self.log.debug(download_ids)
            count = api.get_number_of_downloads(context, download_ids)

            # Return simple <span> with result.
            return html.span(to_unicode(count), class_ = "downloads_count")

        elif name == 'ListDownloads' or name == 'FeaturedDownloads' or name == 'ListFeaturedDownloads':

            # Determine wiki page name.
            page_name = formatter.req.path_info[6:]

            # Create request context.
            context = Context.from_request(formatter.req)('downloads-wiki')

            # Get database access.
            db = self.env.get_db_cnx()
            context.cursor = db.cursor()

            # Get API object.
            api = self.env[DownloadsApi]

            # Get form values.
            order = context.req.args.get('order') or 'id'
            desc = context.req.args.get('desc') or '1'

            # Validate input
            if order not in self.all_fields:
                return system_message("%s: Invalid order by" % name)
            if desc not in ('0', '1'):
                return system_message("%s: Invalid desc" % name)

            # Prepare template data.
            data = {}
            data['order'] = order
            data['desc'] = desc
            data['has_tags'] = self.env.is_component_enabled('tractags.api.TagEngine')
            if name == 'ListDownloads':
                data['downloads'] = api.get_downloads(context, order, desc)
            else:
                data['downloads'] = api.get_featured_downloads(context, order, desc)
            data['visible_fields'] = [(visible_field, None) for visible_field in self.visible_fields]
            data['page_name'] = page_name

            # Return rendered template.
            return to_unicode(Chrome(self.env).render_template(formatter.req,
              'wiki-downloads-list.html', {'downloads' : data}, 'text/html',
              True))
        elif name == 'CustomListDownloads' or name == 'CustomFeaturedDownloads' or name == 'CustomListFeaturedDownloads':

            if not content:
                return ''

            args = content.split(',')
            if len(args) == 0:
                return system_message("%s: Argument missing" % name)

            # Determine wiki page name.
            page_name = formatter.req.path_info[6:]

            # Create request context.
            context = Context.from_request(formatter.req)('downloads-wiki')

            # Get database access.
            db = self.env.get_db_cnx()
            context.cursor = db.cursor()

            # Get API object.
            api = self.env[DownloadsApi]

            # Get form values.
            order = context.req.args.get('order') or 'id'
            desc = context.req.args.get('desc') or '1'

            # Validate input
            if order not in self.all_fields:
                return system_message("%s: Invalid order by" % name)
            if desc not in ('0', '1'):
                return system_message("%s: Invalid desc" % name)

            attr_re = re.compile('(%s)=(.+)' % '|'.join(self.all_fields))

            # Prepare template data.
            data = {}
            data['order'] = order
            data['desc'] = desc
            data['has_tags'] = self.env.is_component_enabled('tractags.api.TagEngine')
            data['page_name'] = page_name
            if name == 'CustomListDownloads':
                data['downloads'] = api.get_downloads(context, order, desc)
            else:
                data['downloads'] = api.get_featured_downloads(context, order, desc)
            data['visible_fields'] = []
            while args:
                arg = args.pop(0).strip()
                match = attr_re.match(arg)
                if match:
                    key, val = match.groups()
                else:
                    key = arg
                    val = None
                if key in self.all_fields:
                    data['visible_fields'].append((key, val))

            # Return rendered template.
            return to_unicode(Chrome(self.env).render_template(formatter.req,
              'wiki-downloads-list.html', {'downloads' : data}, 'text/html',
              True))

    # Internal functions

    def _download_link(self, formatter, ns, params, label):
        if ns == 'download':
            if formatter.req.perm.has_permission('DOWNLOADS_VIEW'):
                # Create context.
                context = Context.from_request(formatter.req)('downloads-wiki')
                db = self.env.get_db_cnx()
                context.cursor = db.cursor()

                # Get API component.
                api = self.env[DownloadsApi]
                by_id = False
                # Get download.
                if params.strip().isdigit():
                    download = api.get_download(context, params)
                    by_id = True
                else:
                    download = api.get_download_by_file(context, params)

                if download:
                    # Get url part to put after "[project]/downloads/"
                    file_part = download['id'] if by_id else download['file']

                    if formatter.req.perm.has_permission('DOWNLOADS_VIEW',
                      Resource('downloads', download['id'])):
                        # Return link to existing file.
                        return html.a(label, href = formatter.href.downloads(
                          file_part), title = '%s (%s)' % (download['file'],
                          pretty_size(download['size'])))
                    else:
                        # File exists but no permission to download it.
                        html.a(label, href = '#', title = '%s (%s)' % (
                          download['file'], pretty_size(download['size'])),
                          class_ = 'missing')
                else:
                    # Return link to non-existing file.
                    return html.a(label, href = '#', title = 'File not found.',
                      class_ = 'missing')
            else:
                # Return link to file to which is no permission.
                return html.a(label, href = '#', title = 'No permission to file.',
                   class_ = 'missing')
