#!/usr/bin/env python
# -*- coding: utf8 -*-
import	os

import 	re

import  regex

import  rfc3987

import  threading

from    plone.synchronize       import  synchronized

from    plone.memoize       	import  volatile

import 	pprint

import 	dns.resolver

from 	contextlib   		import closing

import	colorama

import 	pyinotify

import  subprocess

import 	hashlib

import	shared_infrastructure

class AgnosticConfiguration():

    _configurations_lock           	=       threading.RLock()

    _comment_pattern			= 	'''^\s*(?P<comment>#+)'''

    @staticmethod
    def add_to_configuration( 
        d, 
        l_mapping,
        d_configurations,
        filepath,
        current_server, 
        current_port, 
        current_mapping_type,
    ):
        d_configurations.setdefault( 
            current_server, 
            {} 
        ).setdefault( 
            current_port, 
            {} 
        ).setdefault( 
            current_mapping_type, 
            { 
                'times': { 
                    'ctime': '%s' % ( os.path.getctime( filepath ) ),
                    'mtime': '%s' % ( os.path.getmtime( filepath ) ),
                }, 
                'mappings': [] 
            } 
        )[ 'mappings' ].append( 
            l_mapping( d )
        )


    _mount_pattern			= 	\
        '''^\s*%s\s+%s''' % (
            rfc3987.format_patterns(
                URI		= 'src_URI', 
            )['URI'],
            rfc3987.format_patterns(
                URI		= 'dst_URI', 
            )['URI'],
    )

    @staticmethod
    def process_uri_for_mount(
        self,
        d,
        filepath,
        line,
        server,
        port,
        mapping_type,
        d_configurations,
        l_bad_configurations,
    ):
        shared_infrastructure.common_process_uri( 
            lambda: self._root_agnostic_configuration,  
            d, 
            line, 
            server, 
            port,
            mapping_type, 
            l_bad_configurations, 
            'src_'
        )

        shared_infrastructure.common_process_uri( 
            lambda: self._root_agnostic_configuration,  
            d, 
            line, 
            server, 
            port, 
            mapping_type, 
            l_bad_configurations, 
            'dst_' 
        )

        shared_infrastructure.listen_ssl_process_uri( 
            lambda: self._root_agnostic_configuration,  
            lambda: self._ssl_configuration,
            d, 
            line, 
            server, 
            port, 
            mapping_type,
            l_bad_configurations, 
            'src_'
        )

        AgnosticConfiguration.add_to_configuration( 
            d, 
            lambda d: {
                        'src': d[ 'src_URI' ],
                        'dst': d[ 'dst_URI' ],
                    }, 
            d_configurations,
            filepath,
            server, 
            port, 
            mapping_type, 
        )


    _unmount_pattern			= 	\
        '''^\s*%s''' % (
            rfc3987.format_patterns(
                URI		= 'URI', 
            )['URI'],
    )
        
    @staticmethod
    def process_uri_for_unmount(
        self,
        d,
        filepath,
        line,
        server,
        port,
        mapping_type,
        d_configurations,
        l_bad_configurations,
    ):
        shared_infrastructure.common_process_uri( 
            lambda: self._root_agnostic_configuration,
            d, 
            line, 
            server, 
            port,
            mapping_type, 
            l_bad_configurations, 
            ''
        )

        shared_infrastructure.listen_ssl_process_uri( 
            lambda: self._root_agnostic_configuration,
            lambda: self._ssl_configuration,
            d, 
            line, 
            server, 
            port, 
            mapping_type,
            l_bad_configurations, 
            '' 
        )

        AgnosticConfiguration.add_to_configuration( 
            d, 
            lambda m: { 
                'uri': d[ 'URI' ]
            },
            d_configurations,
            filepath,
            server, 
            port, 
            mapping_type, 
        )


    _redirect_pattern			= 	\
        '''^\s*%s\s+%s''' % (
            rfc3987.format_patterns(
                URI		= 'src_URI', 
            )['URI'],
            rfc3987.format_patterns(
                URI		= 'dst_URI', 
            )['URI'],
    )

    @staticmethod
    def process_uri_for_redirect(
        self,
        d,
        filepath,
        line,
        server,
        port,
        mapping_type,
        d_configurations,
        l_bad_configurations,
    ):
        shared_infrastructure.common_process_uri( 
            lambda: self._root_agnostic_configuration,
            d, 
            line, 
            server, 
            port,
            mapping_type, 
            l_bad_configurations, 
            'src_'
        )

        shared_infrastructure.common_process_uri( 
            lambda: self._root_agnostic_configuration,
            d, 
            line, 
            server, 
            port, 
            mapping_type, 
            l_bad_configurations, 
            'dst_' 
        )

        shared_infrastructure.listen_ssl_process_uri( 
            lambda: self._root_agnostic_configuration,
            lambda: self._ssl_configuration,
            d, 
            line, 
            server, 
            port, 
            mapping_type,
            l_bad_configurations, 
            'src_' 
        )

        AgnosticConfiguration.add_to_configuration( 
            d, 
            lambda d: {
                        'src': d[ 'src_URI' ],
                        'dst': d[ 'dst_URI' ],
                    }, 
            d_configurations,
            filepath,
            server, 
            port, 
            mapping_type, 
        )


    def __init__(
        self, 
        root_agnostic_configuration,
        resolver_conf,
        mount_filename,
        unmount_filename,
        redirect_filename,
        restart_nginx,
        ssl_configuration
    ):

        self._root_agnostic_configuration	= root_agnostic_configuration

        self._resolver_conf			= resolver_conf

        self._mount_filename			= mount_filename

        self._unmount_filename			= unmount_filename

        self._redirect_filename			= redirect_filename

        self._d_l_process_uri		= 				\
            {
                self._mount_filename		: AgnosticConfiguration.process_uri_for_mount,
                self._unmount_filename		: AgnosticConfiguration.process_uri_for_unmount,
                self._redirect_filename		: AgnosticConfiguration.process_uri_for_redirect,
            }

        self._restart_nginx			= restart_nginx

        self._resolver				= None

        self._ssl_configuration			= ssl_configuration

        # Gestion de iNotify	
        wm 					= pyinotify.WatchManager() 
	mask 					= 				\
            pyinotify.IN_MODIFY 	| 					\
            pyinotify.IN_CREATE 	| 					\
            pyinotify.IN_DELETE 	| 					\
            pyinotify.IN_ATTRIB 	| 					\
            pyinotify.IN_MOVED_TO	|					\
            pyinotify.IN_MOVED_FROM


        class EventHandler( pyinotify.ProcessEvent ):


             def process_evt( o, event ):

                 def restart_nginx():

                      try:
    
                          subprocess.call( self._restart_nginx, shell = True )
    
                      except: 
    
                          self._l_bad_configurations.append( ( '%s error' % ( self._restart_nginx ), ) )
    
                          shared_infrastructure.cache_container_agnostic_configuration.clear()
                          shared_infrastructure.cache_container_nginx_fs.clear()

                 path_elements = \
                     filter( 
                         None, 
                         event.pathname[  
                             len( self._root_agnostic_configuration.rstrip( os.sep ) + os.sep ):
                         ].split( os.sep )
                     )

                 if len( path_elements ) == 0 and event.mask & pyinotify.IN_ATTRIB:

                     self.load_configurations( reload_without_version_control = True )

                     return restart_nginx()

                 if 								\
                     event.dir						and	\
                     ( 
                         len( path_elements	) == 1			or	\
                         len( path_elements	) == 2
                     ):

                     if self.load_configurations( reload_without_version_control = False ):

                         return restart_nginx()


                 if len( path_elements ) != 3:
		     return None

                 if re.match( 
                     '^%s|%s|%s$' % ( 
                         self._mount_filename, 
                         self._unmount_filename, 
                         self._redirect_filename 
                     ),
                     path_elements[ 2 ]
                 ): 

                     if self.load_configurations( reload_without_version_control = False ):

                         return restart_nginx()

                        
             process_IN_MODIFY 		= process_evt

             process_IN_CREATE		= process_evt

             process_IN_DELETE		= process_evt

             process_IN_ATTRIB		= process_evt

             process_IN_MOVED_TO	= process_evt

             process_IN_MOVED_FROM	= process_evt


        self._notifier 				= pyinotify.ThreadedNotifier( wm, EventHandler() )

        self._notifier.coalesce_events()

        wm.add_watch( 
            self._root_agnostic_configuration, 
            mask, 
            rec=True,
            auto_add=True
        )
             
        self._d_configurations 			= {}

        self._l_bad_configurations 		= []

        self.load_configurations()


    def get_notifier( self ):
        return self._notifier
    notifier 			= property( get_notifier, None, None )


    @synchronized( _configurations_lock )
    def get_d_configurations( self ):
        return self._d_configurations
    d_configurations 		= property( get_d_configurations, None, None )


    @synchronized( _configurations_lock )
    def get_l_bad_configurations( self ):
        return self._l_bad_configurations
    l_bad_configurations 	= property( get_l_bad_configurations, None, None )


    @synchronized( _configurations_lock )
    def load_configurations( self, reload_without_version_control = False ):

        d_configurations 	= {}

        l_bad_configurations	= []

        # Obtention d'un resolveur base sur le resolv_conf fouri
        self._resolver		= dns.resolver.Resolver( self._resolver_conf )

        # Recherche des serveurs
        for server in [ 
                       s 
                       for s 
                       in os.listdir( self._root_agnostic_configuration )
                       if os.path.isdir( self._root_agnostic_configuration.rstrip( os.sep ) + os.sep + s )
                      ]:

            # Si le nom ne correspond pas a un nom resolvable
            # la configuration n'est pas prise en compte
	    try:
 	               self._resolver.query( server, 'A' )
            except:
                l_bad_configurations.append( ( '%s not resolvable' % ( server ), self._root_agnostic_configuration, server, ) )
                continue


            # Si le repertoire ne contient pas de configuration
            # de port, la configuration n'est pas prise en compte
            if not os.listdir( self._root_agnostic_configuration.rstrip( os.sep ) + os.sep + server ):
                l_bad_configurations.append( ( '%s no port definition' % ( server ), self._root_agnostic_configuration, server, ) )
                continue

            # Recherche des ports
            for port in [ 
                         p
                         for p
                         in os.listdir( self._root_agnostic_configuration.rstrip( os.sep ) + os.sep + server )
                      ]:

                # Si le repertoire ne correspond pas au format d'un nom de port
                # la configuration n'est pas prise en compte
                try:
                    if not( re.match( '\d{1,5}', port ) and int( p ) <= 65535 ):
                        raise Exception()
                except:
                        l_bad_configurations.append( ( '%s unvalid port format' % ( port ), self._root_agnostic_configuration, server, port ) )
                        continue

                # Si aucun fichier de mapping
                # n'est present, la configuration n'est
                # pas prise en compte

                mount_filepath 		= 						\
                    self._root_agnostic_configuration.rstrip( os.sep ) + os.sep + 	\
                    server + os.sep + 							\
                    port + os.sep + 							\
                    self._mount_filename

                unmount_filepath	= 						\
                    self._root_agnostic_configuration.rstrip( os.sep ) + os.sep + 	\
                    server + os.sep + 							\
                    port + os.sep + 							\
                    self._unmount_filename

                redirect_filepath	= 						\
                    self._root_agnostic_configuration.rstrip( os.sep ) + os.sep + 	\
                    server + os.sep + 							\
                    port + os.sep + 							\
                    self._redirect_filename


                def add_to_configuration(
                    mapping_type,
                    filepath,
                    pattern,
                    ):
                    try:
                        with closing( 
                            open( filepath )
                        ) as f:
        
                            for line in [ l.rstrip() for l in f.readlines() ]:
                                if re.match( AgnosticConfiguration._comment_pattern, line ):
                                    continue
        
                                m = re.match( pattern, line )
                                if not m:
                                    l_bad_configurations.append( 
                                        ( 
                                            'invalid format %s' % ( line ), 
                                            self._root_agnostic_configuration, 
                                            server, 
                                            port, 
                                            mapping_type 
                                        ) 
                                    )
                                    continue
                               
                                try:
                                    self._d_l_process_uri[ mapping_type ]( 
                                        self,
                                        m.groupdict(),
                                        filepath,
                                        line,
                                        server,
                                        port, 
                                        mapping_type,
                                        d_configurations, 
                                        l_bad_configurations, 
                                    )
                                except:
                                    import traceback
                                    traceback.print_exc()
                                    continue

                                
                    except:
                        pass

                if \
                    not os.path.isfile( mount_filepath ) 			and	\
                    not os.path.isfile( unmount_filepath ) 			and 	\
                    not os.path.isfile( redirect_filepath ):
                   l_bad_configurations.append( 
                       ( 
                           'no %s or %s or %s file' % \
                               ( 
                                   self._mount_filename, 
                                   self._unmount_filename, 
                                   self._redirect_filename 
                               ), 
                           self._root_agnostic_configuration, 
                           server, 
                           port 
                       ) 
                   )
                   continue

                add_to_configuration( 
                    self._mount_filename, 	
                    mount_filepath, 	
                    AgnosticConfiguration._mount_pattern, 		
                )

                add_to_configuration( 
                    self._unmount_filename, 	
                    unmount_filepath,	
                    AgnosticConfiguration._unmount_pattern, 	
                )

                add_to_configuration( 
                    self._redirect_filename, 	
                    redirect_filepath, 	
                    AgnosticConfiguration._redirect_pattern, 	
                )

        if len( d_configurations ) == 0:
            l_bad_configurations.append( ( 'no configuration available', self._root_agnostic_configuration, ) )

        if  													\
                 reload_without_version_control 								\
             or													\
                 self.get_version_configurations( d_configurations ) <> self.get_version_configurations() 	\
             or													\
                 hashlib.sha1( repr( l_bad_configurations ) ).hexdigest() <> hashlib.sha1( repr( self._l_bad_configurations ) ).hexdigest():

            self._d_configurations         =       d_configurations
            self._l_bad_configurations     =       l_bad_configurations
            shared_infrastructure.cache_container_agnostic_configuration.clear()
            shared_infrastructure.cache_container_nginx_fs.clear()

            #pprint.pprint( self._d_configurations )

            return True

        return False

        #pprint.pprint( self._d_configurations )


    @synchronized( _configurations_lock )
    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_agnostic_configuration )
    def get_id_configurations( self ):

        return reduce(
            list.__add__,
            map( 
                lambda ( server, portsv ): reduce( 
                    list.__add__, 
                    map( 
                       lambda ( port, mappings_typev ): map(
                           lambda mapping_type: [ server, port, mapping_type ],
                               mappings_typev.keys(),
                           ),
                           portsv.items()
                    )
                ), 
                self._d_configurations.items()
            ) if self._d_configurations.items() else [ [] ]
        )
    id_configurations 	= property( get_id_configurations, None, None )


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_agnostic_configuration )
    def filter_agnostic_id_configurations( 
        self, 
        pattern_server 		= '.*', 
        pattern_port 		= '.*', 
        pattern_mapping_type 	= '.*' 
    ):
        return filter(
            lambda ( server, port, mapping_type ): \
                re.match( pattern_server, server ) 	and \
                re.match( pattern_port, port ) 		and \
                re.match( pattern_mapping_type, mapping_type ),
            self.id_configurations
        )

    
    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_agnostic_configuration )
    def get_list_agnostic_configurations_filenames( 
        self, 
        pattern_server 		= '.*', 
        pattern_port 		= '.*', 
        pattern_mapping_type 	= '.*' 
    ):
        return map( 
            lambda ( server, port, mapping_type ): 			\
                self._root_agnostic_configuration.rstrip( os.sep ) + os.sep +	
                server + os.sep +				
                port + os.sep +					
                mapping_type,
            self.filter_agnostic_id_configurations( pattern_server, pattern_port, pattern_mapping_type )
        )

    
    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_agnostic_configuration )
    def get_last_time(
        self, 
        fct,
        pattern_server 		= '.*', 
        pattern_port 		= '.*', 
        pattern_mapping_type 	= '.*' 
    ):
        d_pattern_mapping_type_2_pattern_mapping_type	= {
           self._mount_filename		: self._mount_filename,
           self._unmount_filename	: self._unmount_filename,
           self._redirect_filename	: self._mount_filename + '|' + self._redirect_filename,
	} 

        return max( 
            map( 
                lambda filename: fct( filename ),
                self.get_list_agnostic_configurations_filenames( 
                    pattern_server, 
                    pattern_port, 
                    d_pattern_mapping_type_2_pattern_mapping_type.get( pattern_mapping_type, pattern_mapping_type ) 
                ) 
            ) or [ 0 ]
        )
        return


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_agnostic_configuration )
    def get_last_atime(
        self, 
        pattern_server 		= '.*', 
        pattern_port 		= '.*', 
        pattern_mapping_type 	= '.*' 
    ):

        return self.get_last_time( 
            os.path.getatime, 
            pattern_server, 
            pattern_port, 
            pattern_mapping_type 
        ) 
    
    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_agnostic_configuration )
    def get_last_ctime(
        self, 
        pattern_server 		= '.*', 
        pattern_port 		= '.*', 
        pattern_mapping_type 	= '.*' 
    ): 

        return self.get_last_time( 
            os.path.getctime, 
            pattern_server, 
            pattern_port, 
            pattern_mapping_type 
        ) 


    @volatile.cache( shared_infrastructure.cache_key, lambda *args: shared_infrastructure.cache_container_agnostic_configuration )
    def get_last_mtime(
        self, 
        pattern_server 		= '.*', 
        pattern_port 		= '.*', 
        pattern_mapping_type 	= '.*' 
    ): 

        return self.get_last_time(
            os.path.getmtime,
            pattern_server,
            pattern_port,
            pattern_mapping_type
        ) 
 

    @synchronized( _configurations_lock )
    def get_version_configurations( self, d_configurations = {} ):

        if d_configurations == None:
            d_configurations = self._d_configurations

        
        return \
            hashlib.sha1(
                ' '.join(
                    reduce(
                        list.__add__,
                        map( 
                            lambda ( server, portsv ): \
                                reduce( 
                                    list.__add__, 
                                    map( 
                                       lambda ( port, mappings_typev ): \
                                           reduce( 
                                                list.__add__, 
                                                map(
                                                    lambda ( mapping_type, infosv ): \
                                                        reduce(
                                                            list.__add__,
                                                            map(
                                                                lambda all_infos: \
                                                                     [ server, port, mapping_type ] + all_infos,
                                                                map(
                                                                    lambda ( mappings ): \
            							        reduce(
                                                                            list.__add__,
                                                                            #[ 
                                                                            #    [ k, v ] 
                                                                            #    for k, v 
                                                                            #    in sorted( 
                                                                            #        infosv[ 'times' ].items()
                                                                            #    ) 
                                                                            #] +
                                                                            map(
                                                                                lambda ( k, v ): [ k, v ],
                                                                                sorted( mappings.items() )
                                                                            ) if mappings.items() else [ [] ]
                                                                        ),
                                                                    infosv[ 'mappings' ]
                                                                )
                                                            )
                                                        ),
                                                    sorted( mappings_typev.items() )
                                                ) if mappings_typev.items() else [ [] ]
                                           ),
                                           sorted( portsv.items() )
                                    ) if portsv.items() else [ [] ]
                                ), 
                            sorted( d_configurations.items() )
                        ) if d_configurations.items() else [ [] ]
                    )
                )
            ).hexdigest()
