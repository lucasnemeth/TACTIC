###########################################################
#
# Copyright (c) 2005, Southpaw Technology
#                     All Rights Reserved
#
# PROPRIETARY INFORMATION.  This software is proprietary to
# Southpaw Technology, and is not to be reproduced, transmitted,
# or disclosed in any way without written permission.
#
#
#


#import tacticenv
import sys, re, getopt, os, shutil

#from pyasm.command import Command
from pyasm.search import Search, SObject, DbContainer, Sql
from pyasm.common import Container, Environment

__all__ = ['Upgrade']

class Upgrade(object):

    def __init__(my, version, is_forced=False, project_code=None, quiet=False, is_confirmed=False):
        my.to_version = version
        my.is_forced = is_forced
        my.is_confirmed = is_confirmed

        my.project_code = project_code
        my.quiet = quiet

        
    def execute(my):
        error_list = []
        from pyasm.biz import Project
        Project.clear_cache()

        sthpw_search = Search("sthpw/project")
        sthpw_search.add_filter('code','sthpw')
        sthpw_search.set_show_retired(True)
        sthpw_proj = sthpw_search.get_sobject()

        search = Search("sthpw/project")
        if my.project_code:
            search.add_filter("code", my.project_code)
        else:
            #search.add_enum_order_by("type", ['sthpw','prod','game','design','simple', 'unittest'])
            search.add_enum_order_by("code", ['sthpw'])
        projects = search.get_sobjects()

        project_codes = SObject.get_values(projects, 'code')
        # append sthpw project in case it's retired
        if 'sthpw' not in project_codes and sthpw_proj:
            if not my.project_code:
                projects.insert(0, sthpw_proj)
            sthpw_proj.reactivate()



        current_dir = os.getcwd()
        tmp_dir = Environment.get_tmp_dir()
        output_file = '%s/upgrade_output.txt' % tmp_dir
        if not os.path.exists(tmp_dir):
            os.makedirs(tmp_dir)
        elif os.path.exists(output_file):
            os.unlink(output_file)
        ofile = open(output_file, 'w')

        import datetime
        ofile.write('Upgrade Time: %s\n\n' %datetime.datetime.now())



        # dynamically generate
        #sql = DbContainer.get(code)
        database_type = Sql.get_default_database_type()
        #if database_type in ['Sqlite', 'MySQL']:
        if database_type != "PostgreSQL":
            # general an upgrade
            import imp

            namespaces = ['default', 'simple', 'sthpw', 'config']
            for namespace in namespaces:
                if database_type == 'Sqlite':
                    from pyasm.search.upgrade.sqlite import convert_sqlite_upgrade
                    file_path = convert_sqlite_upgrade(namespace)
                elif database_type == 'MySQL':
                    from pyasm.search.upgrade.mysql import convert_mysql_upgrade
                    file_path = convert_mysql_upgrade(namespace)
                elif database_type == 'SQLServer':
                    from pyasm.search.upgrade.sqlserver import convert_sqlserver_upgrade
                    file_path = convert_sqlserver_upgrade(namespace)
                elif database_type == 'Oracle':
                    file_path = convert_oracle_upgrade(namespace)
                else:
                    raise Exception("Database type not implemented here")

                (path, name) = os.path.split(file_path)
                (name, ext) = os.path.splitext(name)
                (file, filename, data) = imp.find_module(name, [path])
                module = imp.load_module(name, file, filename, data)

                class_name = "%s%sUpgrade" % (database_type,namespace.capitalize())
                exec("%s = module.%s" % (class_name, class_name) )



        # load all the default modules
        from pyasm.search.upgrade.project import *

        for project in projects:
            
            code = project.get_code()
            if code == "sthpw":
                type = "sthpw"
            else:
                type = project.get_type()

            if not type:
                type = 'default'


            if not my.quiet:
                print project.get_code(), type
                print "-"*30

            # if the project is admin, the just ignore for now
            if code == 'admin':
                continue
            
            if not project.database_exists():
                ofile.write("*" * 80 + '\n')
                msg =  "Project [%s] does not have a database\n"% project.get_code()
                ofile.write(msg)
                print msg
                ofile.write("*" * 80 + '\n\n')
                continue


            upgrade = None

            if database_type != 'PostgreSQL':
                upgrade_class = "%s%sUpgrade" % (database_type, type.capitalize())
                conf_upgrade = eval("%sConfigUpgrade()" % database_type)
            else:
                upgrade_class = "%sUpgrade" % type.capitalize()
                conf_upgrade = eval("ConfigUpgrade()")
            upgrade = eval("%s()" % upgrade_class)

            # upgrade config (done for every project but sthpw)
            conf_upgrade.set_project(project.get_code())
            conf_upgrade.set_to_version(my.to_version)
            conf_upgrade.set_forced(my.is_forced)
            conf_upgrade.set_quiet(my.quiet)
            conf_upgrade.set_confirmed(my.is_confirmed)
            conf_upgrade.execute()
            
            # append the errors for each upgrade
            key = '%s|%s' %(project.get_code(), conf_upgrade.__class__.__name__)
            error_list.append((conf_upgrade.__class__.__name__, project.get_code(), \
                Container.get_seq(key)))


            # perform the upgrade to the other tables
            if upgrade:
                upgrade.set_project(project.get_code() )
                upgrade.set_to_version(my.to_version)
                upgrade.set_forced(my.is_forced)
                upgrade.set_quiet(my.quiet)
                upgrade.set_confirmed(my.is_confirmed)
                #Command.execute_cmd(upgrade)
                # put each upgrade function in its own transaction
                # carried out in BaseUpgrade
                upgrade.execute()
                
                # append the errors for each upgrade
                key = '%s|%s' %(project.get_code(), upgrade.__class__.__name__)
                error_list.append((upgrade.__class__.__name__, project.get_code(), \
                    Container.get_seq(key)))

            from pyasm.search import DatabaseImpl
            project.set_value("last_db_update", DatabaseImpl.get().get_timestamp_now(), quoted=False)
            
            if project.has_value('last_version_update'):
                last_version = project.get_value('last_version_update')
                if my.to_version > last_version:
                    project.set_value("last_version_update", my.to_version)
            else: 
                # it should be getting the upgrade now, redo the search
                print "Please run upgrade_db.py again, the sthpw db has just been updated"
                return
            project.commit(triggers=False)



        # print the errors for each upgrade
        for cls_name, project_code, errors in error_list:
            if not my.quiet:
                print
                print "Errors for %s [%s]:" %(project_code, cls_name)
            ofile.write("Errors for %s [%s]:\n" %(project_code, cls_name))
            if not my.quiet:
                print "*" * 80
            ofile.write("*" * 80 + '\n')
            for func, error in errors:
                if not my.quiet:
                    print '[%s]' % func
                    print "-" * 70
                    print error
                ofile.write('[%s]\n' % func)
                ofile.write("-" * 70 + '\n')
                ofile.write('%s\n' %error)
        ofile.close()

        if my.quiet:
            print "Please refer to the upgrade_output.txt file for any upgrade messages."
            print
        # handle sthpw database separately.  This ensures that the project entry
        # gets created if none exists.
        #print "sthpw"
        #print "-"*30
        #upgrade = SthpwUpgrade()
        #upgrade.set_project("sthpw")
        #Command.execute_cmd(upgrade)

        # update the template zip files
        data_dir = Environment.get_data_dir(manual=False)
        dest_dir = '%s/templates' %data_dir
        if os.path.exists(dest_dir):
            install_dir = Environment.get_install_dir()
            src_code_template_dir = '%s/src/install/start/templates' %install_dir
            if os.path.exists(src_code_template_dir):
                zip_files = os.listdir(src_code_template_dir)
                io_errors = False
                for zip_file in zip_files:
                    if not zip_file.endswith(".zip"):
                        continue
                    try:
                        src_file = '%s/%s' %(src_code_template_dir, zip_file)
                        dest_file = '%s/%s' %(dest_dir, zip_file)
                        shutil.copyfile(src_file, dest_file)
                    except IOError, e:
                        print e
                        io_errors = True
                if not io_errors:
                    print "Default project template files have been updated."
                else:
                    print "There was a problem copying the default template files to <TACTIC_DATA_DIR>/templates."


    



