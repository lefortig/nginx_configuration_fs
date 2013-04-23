#!/usr/bin/env python
# -*- coding: utf8 -*-
from 	errno 			import ENOENT, EISDIR, EAGAIN
from 	stat			import S_IFDIR, S_IFREG
import 	sys
from 	fuse 			import FuseOSError, Operations, LoggingMixIn

import	os

from	math			import ceil

import 	re

from    plone.memoize       	import  volatile

import 	pprint

import 	dns.resolver

import	colorama

import 	pyinotify

import  subprocess

from 	jinja2 			import Environment, PackageLoader

import	shared_infrastructure

import	ssl_configuration

class NGINXConfigurationFS(LoggingMixIn, Operations):

    __READ_CTX__			= 'READ_CTX'
    __ATTR_CTX__			= 'ATTR_CTX'
    __ID_SERVER__			= 'ID_SERVER'
    __ID_PORT__				= 'ID_PORT'
    __ID_MAPPING_TYPE__			= 'ID_MAPPING_TYPE'

    def __init__(
        self,
        agnostic_configuration,
        root_nginx_configuration,
        uid_owner,
        gid_owner,
        resolver_conf,
        mount_filename,
        unmount_filename,
        redirect_filename,
        error_status_filename,
        restart_nginx,
        ssl_configuration,
        url2app_configuration,
    ):

        self._agnostic_configuration	= agnostic_configuration
        self._root_nginx_configuration	= root_nginx_configuration
        self._uid_owner			= uid_owner
        self._gid_owner			= gid_owner
        self._resolver_conf		= resolver_conf
        self._resolver			= dns.resolver.Resolver( self._resolver_conf )
        self._resolver.query    	= shared_infrastructure.catch_NoNamesservers( self._resolver.query )
        self._mount_filename		= mount_filename
        self._unmount_filename		= unmount_filename
        self._redirect_filename		= redirect_filename
        self._error_status_filename	= error_status_filename
        self._restart_nginx		= restart_nginx
        self._ssl_configuration		= ssl_configuration

        self._l_bad_configurations	= []

        self._pattern_converted_conf_filenames	= \
           '^(?P<server>.*)-(?P<port>\d+)\.conf$'

        self._pattern_converted_map_filenames	= \
            '^(?P<mapping_type>' + \
            '%s|%s|%s' % ( 
                self._mount_filename, 
                self._unmount_filename, 
                self._redirect_filename, 
            ) + ')-(?P<server>.*)-(?P<port>\d+)\.map$'

        # Getion des templates de read
        # Creation de l'nevironement des templates
        self._env				= 	\
            Environment(
                loader	= 			  	\
                    PackageLoader( 
                        __name__, 
                        'templates'
                    )
            )

        # Gestion des interactions cross mapping
        # Les tableaux agnostic vers virtuel permettent de calculer
        # les dependances engendrer par les modificatinos dans agnostic
        self._d_id_server_agnostic_2_virtual		= {}
        self._d_id_port_agnostic_2_virtual		= {}
        self._d_id_mapping_type_agnostic_2_virtual	= {
            self._mount_filename:    [
                self._mount_filename,
                self._redirect_filename
            ],
            self._redirect_filename: [
                self._redirect_filename,
                self._mount_filename
            ],
            self._unmount_filename: [
                self._unmount_filename,
                self._mount_filename
            ],
        }

        # la gestion cross mapping dnas le sens virtuel a agnostic
        # est plus compliquee
        # Au premier niveau, elle est contextualisee
        # NGINXConfigurationFS.__ATTR_CTX__ pour le cross mapping
        # concernant l'obtention des attributs de fichiers (getattr)
        # NGINXConfigurationFS.__READ_CTX__ pour le crosss mapping
        # concernant la lecture (read)
        # Elle est ensuite categorisee par id (server, port, mapping_ype).
        # Puis les cross mappings eux-memes sont exprimes
        self._d_id_virtual_2_agnostic				= {
            NGINXConfigurationFS.__ATTR_CTX__:			\
	        {
                     NGINXConfigurationFS.__ID_SERVER__:	\
                         {
                         },
                     NGINXConfigurationFS.__ID_PORT__:		\
                         {
                         },
                     NGINXConfigurationFS.__ID_MAPPING_TYPE__:	\
                         {
                             self._mount_filename:		\
                                 [
                                     self._mount_filename,
                                     self._redirect_filename,
                                     self._unmount_filename,
                                 ],
                             self._redirect_filename: 		\
                                 [
                                     self._redirect_filename,
                                     self._mount_filename
                                 ],
                             self._unmount_filename: 		\
                                 [ self._unmount_filename ],
                         },
                },
            NGINXConfigurationFS.__READ_CTX__:			\
	        {
                     NGINXConfigurationFS.__ID_SERVER__:	\
                         {
                         },
                     NGINXConfigurationFS.__ID_PORT__:		\
                         {
                         },
                     NGINXConfigurationFS.__ID_MAPPING_TYPE__:	\
                         {
                             self._mount_filename:		\
                                 [ self._mount_filename ],
                             self._redirect_filename: 		\
                                 [ self._redirect_filename ],
                             self._unmount_filename: 		\
                                 [ self._unmount_filename ],
                         },
                },
        }

        wm 					= pyinotify.WatchManager() 
	mask 					= pyinotify.IN_MODIFY

        # Gestion du repertoire des templates
        def get_template_dir( template_name ):
            try:
               return \
                    self._env.get_template(
                        template_name
                    ).filename[ :-len( template_name ) ] 
            except:
                return None

        def add_templates_watches():
            wm.add_watch( 
                list(
                    set(
                        filter(
                            None,
                            map(
                                get_template_dir,
                                self.list_template_names
                            )
                        )
                    )
                ),
                mask, 
                rec=True,
                auto_add=True
            )

        class TemplateEventHandler( pyinotify.ProcessEvent ):

             def process_evt( o, event ):

                 if not event.dir and 				\
                    not event.pathname[ 
                            event.pathname.rfind( 
                                os.sep + 'templates' + os.sep 
                            ) + 
                            len( 
                                os.sep + 'templates' + os.sep 
                            ): ] in self.list_template_names:
                        return None

                 self._l_bad_configurations 	= []

                 self._env.cache.clear()

                 shared_infrastructure.cache_container_nginx_fs.clear()

                 try:

                     subprocess.call( self._restart_nginx, shell = True )

                 except: 

                     self.l_bad_configurations.append( ( '%s error' % ( self._restart_nginx ), ) )

                     shared_infrastructure.cache_container_agnostic_configuration.clear()

                     shared_infrastructure.cache_container_nginx_fs.clear()

             process_IN_MODIFY	= process_evt


        self._template_notifier 				= pyinotify.ThreadedNotifier( wm, TemplateEventHandler() )

        self._template_notifier.coalesce_events()

        add_templates_watches()

        self._template_notifier.start()
	
        self._agnostic_configuration.notifier.start()

        self._ssl_configuration.notifier.start()


    def get_uid_owner( self ):
        return self._uid_owner
    uid_owner 	= property( get_uid_owner, None, None )


    def get_gid_owner( self ):
        return self._gid_owner
    gid_owner 	= property( get_gid_owner, None, None )

    def get_l_bad_configurations( self ):
        return self._l_bad_configurations
    l_bad_configurations        = property( get_l_bad_configurations, None, None )

    def get_have_bad_configurations( self ):
        return 									\
            len( self.l_bad_configurations ) 				+ 	\
            len( self._agnostic_configuration.l_bad_configurations ) 	+  	\
            len( self._ssl_configuration.l_bad_configurations )			\
            != 0
    have_bad_configurations = property( get_have_bad_configurations, None, None )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def get_template_name( self, suffix ):
        return '%s.tpl' % ( suffix )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def get_list_template_names( self ):
        return \
            sorted(
                map(
                    self.get_template_name,
                    [
                        'conf',
                        self._mount_filename,
                        self._unmount_filename,
                        self._redirect_filename
                    ]
                )
            )
    list_template_names 		= property( get_list_template_names, None, None )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def get_converted_conf_filename( self, server, port ):
        return '%s-%s.conf' % ( server, port )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def get_list_converted_conf_filenames( self ):

        return sorted(
            list( 
                set(
                    map(
                        lambda ( server, port, mapping_type ): self.get_converted_conf_filename( server, port ), 
                        self._agnostic_configuration.id_configurations
                    )
                )
           )
        )
    list_converted_conf_filenames 	= property( get_list_converted_conf_filenames, None, None )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def get_converted_map_filename( self, server, port, mapping_type ):
        return '%s-%s-%s.map' % ( mapping_type, server, port )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def get_list_converted_map_filenames( self ):

        def process_id_configuration( id_configuration ):

            return 	\
                reduce(
                    list.__add__,
                    reduce(
                        list.__add__,
                        map(
                            lambda server:
                                 map(
                                     lambda port:
                                         map(
                                             lambda mapping_type:
                                                 [ server, port, mapping_type ],
                                                 self._d_id_mapping_type_agnostic_2_virtual.get(
                                                     id_configuration[ 2 ],
                                                     [ id_configuration[ 2 ] ]
                                                 )
                                         ),
                                         self._d_id_port_agnostic_2_virtual.get(
                                             id_configuration[ 1 ],
                                             [ id_configuration[ 1 ] ]
                                         )
                                 ),
                            self._d_id_server_agnostic_2_virtual.get(
                                 id_configuration[ 0 ],
                                 [ id_configuration[ 0 ] ]
                            )
                        )
                    )
                )

        return 		\
            sorted(
                list(
                    set(
                        map(
                            lambda ( server, port, mapping_type ): 	\
                                self.get_converted_map_filename( server, port, mapping_type ),
                            reduce(
                                list.__add__,
                                map(
                                    process_id_configuration,
                                    self._agnostic_configuration.id_configurations
                                ) or [ [] ]
                            )
                        )
                    )
                )
            )

    list_converted_map_filenames 	= property( get_list_converted_map_filenames, None, None )



    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def get_suffix_map( self, server, port ):
        return '%s__%s' % ( server.replace( '-', '_' ), port )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def get_id_from_filename_elements( self, path_elements, ctx ):
        """
           path_elements est une liste d'elements composants le nom du fichier
           with_resolved_cross_mapping permet de specifier qu'on recherche
           le fichier correspondant uniquement aux criteres du path_elements
           ou qu'on applique les maping provenant des tableaux *virtual_2_agnostic_attrctx
        """
        if 	len( path_elements ) == 0:
            return ( '.*', '.*', '.*' )
        elif 	len( path_elements ) == 1:

            if path_elements[ 0 ] == self._error_status_filename:
                return ( '.*', '.*', '.*' )

            m_id	= re.match(
                self._pattern_converted_conf_filenames, 
                path_elements[ 0 ] 
            ) 

            if m_id:

                return ( 
                    '|'.join(
                        self._d_id_virtual_2_agnostic[ ctx ][ NGINXConfigurationFS.__ID_SERVER__ ].get(
                            m_id.group( 'server' ),
                            [ m_id.group( 'server' ) ]
                        )
                    ),
                    '|'.join(
                        self._d_id_virtual_2_agnostic[ ctx ][ NGINXConfigurationFS.__ID_PORT__ ].get(
                            m_id.group( 'port' ),
                            [ m_id.group( 'port' ) ]
                        )
                    ),
                    '.*',
                )

            m_id	= re.match( 
                self._pattern_converted_map_filenames, 
                path_elements[ 0 ] 
            )

            if m_id:

                return (
                    '|'.join(
                        self._d_id_virtual_2_agnostic[ ctx ][ NGINXConfigurationFS.__ID_SERVER__ ].get(
                            m_id.group( 'server' ),
                            [ m_id.group( 'server' ) ]
                        )
                    ),
                    '|'.join(
                        self._d_id_virtual_2_agnostic[ ctx ][ NGINXConfigurationFS.__ID_PORT__ ].get(
                            m_id.group( 'port' ),
                            [ m_id.group( 'port' ) ]
                        )
                    ),
                    '|'.join(
                        self._d_id_virtual_2_agnostic[ ctx ][ NGINXConfigurationFS.__ID_MAPPING_TYPE__ ].get(
                            m_id.group( 'mapping_type' ),
                            [ m_id.group( 'mapping_type' ) ]
                        )
                    ),
                )

            raise FuseOSError( ENOENT )

        else:

            raise FuseOSError( ENOENT )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def getattr(self, path, fh=None):

        path_elements           = filter( None,  path.split( '/' ) )

        st = dict(
            st_mode	=	( ( S_IFDIR | 0755 ) if len( path_elements ) == 0 else ( S_IFREG | 0644 ) ), 
            st_nlink	=	2, 
            st_size	= 	( 4096 * int( 1 + ceil( len( self.readdir( path ) ) / 4096 ) ) ) if len( path_elements ) == 0 else len( self.read( path, -1, 0, fh ) ),
            st_atime 	= 	self._agnostic_configuration.get_last_atime(
                                    *self.get_id_from_filename_elements(
                                        path_elements,
                                        NGINXConfigurationFS.__ATTR_CTX__
                                    )
                                ),
            st_ctime 	= 	self._agnostic_configuration.get_last_ctime(
                                    *self.get_id_from_filename_elements(
                                        path_elements,
                                        NGINXConfigurationFS.__ATTR_CTX__
                                    )
                                ),
            st_mtime 	= 	self._agnostic_configuration.get_last_mtime(
                                    *self.get_id_from_filename_elements(
                                        path_elements,
                                        NGINXConfigurationFS.__ATTR_CTX__
                                    )
                                ), 
            st_uid	=	self._uid_owner,
            st_gid	=	self._gid_owner,
        )

        return st


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def readdir( self, path, fh = None ):

        path_elements           = filter( None,  path.split( '/' ) )

        if self.get_id_from_filename_elements(
            path_elements,
            True
        ):

            return [ '.', '..' ] +					\
                   self.list_converted_conf_filenames + 		\
                   self.list_converted_map_filenames + 			\
                   ( [ self._error_status_filename ] if 		\
                       self.have_bad_configurations else [] )
                   

    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def read(self, path, size, offset, fh = None ):

        if offset != 0 or size != -1:
            return self.read( path, -1, 0, fh )[ offset:offset+size ]

        path_elements           = filter( None,  path.split( '/' ) )

        if len( path_elements ) == 0:
            raise FuseOSError( EISDIR )


        if len( path_elements ) == 1:

            if path_elements[ 0 ] 	== self._error_status_filename:
                if self.have_bad_configurations: 
                    return self.read_error_status()
                else:
                    raise FuseOSError( ENOENT )

            # Appele vevant une exception si l'entite n'existe pas
            pattern_server, 			\
	    pattern_port, 			\
	    pattern_mapping_type	= 	\
                self.get_id_from_filename_elements(
                    path_elements,
                    NGINXConfigurationFS.__READ_CTX__
                )

            # Si l'element est une configuration
            if path_elements[ 0 ] in self.list_converted_conf_filenames:
                return self.read_conf( pattern_server, pattern_port )

            #if True:
            try:
            # Si l'element est une map
                return self.read_map( pattern_server, pattern_port, pattern_mapping_type )

            except:
                raise FuseOSError( ENOENT )

        raise FuseOSError( ENOENT )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def read_error_status( self ):

        result 	= ''

        d_color = {
            2	: colorama.Fore.RED,
	    3   : colorama.Fore.CYAN,
            4   : colorama.Fore.YELLOW,
        }

        l_bad_id = [ 
            self._agnostic_configuration._root_agnostic_configuration,
            self._ssl_configuration._root_ssl_configuration,
            'FS', 
        ]

        d_bad = {
           self._agnostic_configuration._root_agnostic_configuration:
               self._agnostic_configuration.l_bad_configurations,
           self._ssl_configuration._root_ssl_configuration:
               self._ssl_configuration.l_bad_configurations,
           'FS':
               self.l_bad_configurations
        }

        if self.have_bad_configurations:

            for bad_id in l_bad_id:

                if len( d_bad[ bad_id ] ) != 0:
           
                    result = 											\
                        result +										\
                        ( "## ERRORS from %s ##" % ( bad_id ) ) + os.linesep
    
                    for message in d_bad[ bad_id ]:

                        result = 										\
            	        result +										\
                        	d_color.get( len( message[ 1: ] ), colorama.Fore.WHITE ) +			\
                            ( 
                                ( os.sep.join( map( lambda m: m.rstrip( os.sep ), message[ 1: ] ) ) ) if	\
                                    len( message ) > 1 else 							\
            		        u'ERROR' 
                            ) +										        \
                            u' : ' +										\
                            message[ 0 ] +									\
                            colorama.Fore.RESET + os.linesep

        return result.encode('utf-8')


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def read_conf( self, server, port ):

        l_uniq_upstream	= set()

        return \
            self._env.get_template( 
                self.get_template_name( 'conf' ) 
            ).render( 
                server				= \
		    server,
                port				= \
		    port,
                resolver 			= \
                    self._resolver,
                list_converted_map_filenames	= \
                    self.list_converted_map_filenames,
                suffix_map			= \
                    self.get_suffix_map( 
                        server, 
                        port 
                    ),
                converted_unmount_map_filename	= \
                    self.get_converted_map_filename(
                        server, 
                        port, 
                        self._unmount_filename 
                    ),
                converted_redirect_map_filename	= \
                    self.get_converted_map_filename(
                        server, 
                        port, 
                        self._redirect_filename 
                    ),
                converted_mount_map_filename	= \
                    self.get_converted_map_filename(
                        server, 
                        port, 
                        self._mount_filename 
                    ),
                root_nginx_configuration	= \
                    self._root_nginx_configuration.rstrip( os.sep ) + os.sep,
                ssl_configuration		= \
                    self._ssl_configuration.get_ssl_configuration( server, port ),
                upstream_configuration 		= \
                    filter(
                        lambda d: d[ 'name' ] not in l_uniq_upstream
                        and
                        (
                            l_uniq_upstream.add( d[ 'name' ] ) or
                            True
                        ),
                        [
                            {
                                'name':
                                    d[ 'dst_upstream_name' ],
                                'host':
                                    d[ 'dst_host' ],
                                'port':
                                    d[ 'dst_port' ],
                                'ips':
                                    d[ 'dst_upstream_resolved_ips' ],
                            }
                            for d in
                            self._agnostic_configuration.d_configurations[
                                server
                            ][
                                port
                            ].get(
                                self._mount_filename,
                                {},
                            ).get(
                                'mappings',
                                []
                            )
                        ]
                    ),
        ).encode( 'utf-8' )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_nginx_fs )
    def read_map( self, server, port, mapping_type  ):

        return \
            self._env.get_template( 
                self.get_template_name( mapping_type )
            ).render( 
                server				= \
		    server,
                port				= \
		    port,
                resolver 			= \
                    self._resolver,
                list_converted_map_filenames	= \
                    self.list_converted_map_filenames,
                suffix_map			= \
                    self.get_suffix_map( 
                        server, 
                        port 
                    ),
                mount_configurations		= \
                    self._agnostic_configuration.d_configurations[ 
                        server
                    ][ 
                        port 
                    ].get( 
                        self._mount_filename,
                        {}, 
                    ).get(
                        'mappings',
                        []
                    ),
                unmount_configurations		= \
                    self._agnostic_configuration.d_configurations[ 
                        server
                    ][ 
                        port 
                    ].get( 
                        self._unmount_filename,
                        {}
                    ).get(
                        'mappings',
                        []
                    ),
                redirect_configurations		= \
                    self._agnostic_configuration.d_configurations[ 
                        server
                    ][ 
                        port 
                    ].get( 
                        self._redirect_filename,
                        {}
                    ).get(
                        'mappings',
                        []
                    ),
                ssl_configuration		= \
                    self._ssl_configuration.get_ssl_configuration( server, port ),
        ).encode( 'utf-8' )


    def destroy(self, private_data):

        self._template_notifier.stop()

        self._ssl_configuration.notifier.stop()

        self._agnostic_configuration.notifier.stop()


    access 	= None
    flush 	= None
    getxattr 	= None
    listxattr 	= None
    open	= None
    opendir 	= None
    release 	= None
    releasedir 	= None
    statfs 	= None
