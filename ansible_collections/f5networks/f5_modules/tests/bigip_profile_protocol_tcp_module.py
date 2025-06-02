#!/usr/bin/python3
# -*- coding: utf-8 -*-
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
---
module: bigip_profile_protocol_TCP_module

short_description: Ce module permet la modification, suppression ou création d'une vip

description:
  - Se connecte en ssh via paramiko
  - Envoie la ou les commandes sur le device et retourne les lignes affichées par l'équipement.

version_added: '0.1.0'

authors:
  - Theo Laurent (@Theo_Laurent)
  - Benjamin Boussereau (@Benjamin-Boussereau)

options:
  ip:
    description:
      - l'ip de l'équipement sur lequel on souhaite intervenir.
    type: str
    required: true
    
  username:
    description:
      - le login utilisé pour se connecter sur le device.
    type: str
    required: true
    
  password:
    description:
      - le password utilisé pour se connecter sur le device.
    type: str
    required: true
  
  tcp_params:
    description:
      - dictionnaire qui contient les informations du profile TCP telles qu'écrites dans le fichier.
    type: dict
    required: true
  
'''

EXAMPLES = r'''
- name: Affiche la running config
  register: running_conf
  my_namespace.send_command.module_fn_ssh:
    cmd : "show run\n"
    ip : "1.1.1.1"
    username : "my_login"
    password : "my_password"
'''


import paramiko
import sys
import os
import time
import re
from ansible.module_utils.basic import AnsibleModule  

# Foction responsable de l'envoie des commandes ssh sur le server
def fn_ssh(cmdx, server, connection_port, user, pwd):
    # initialisation de la variable de sortie
    output = ""
    # reservation du socket avec le module paramiko SSHClient
    ssh=paramiko.SSHClient()
    # deifinition de la politique de gestion des clé publique des hosts
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # lancement de la connexion ssh sur le server
    ssh.connect(server,connection_port,user,pwd,allow_agent=False,look_for_keys=False)
    # invocation du shell interractif
    shell = ssh.invoke_shell()
    #tempo
    time.sleep(0.5)
    # pour chaque commande de la liste fournie en paramètre divisée sur les retours à la ligne nous lançons cette commande et plaçons le retour du shell dans une variable
    for cm in cmdx.split("\n"):
        cm = cm + "\n"
        shell.send(cm)
        time.sleep(0.5)
        output += shell.recv(65535).decode('utf-8')
    # traitement des résultats pour obtenir une liste lisible
    resp = output.split("\r\n")
    # fermeture du shell et du ssh afin de libérer le socket
    shell.close()
    ssh.close()
    # renvoie de la valeur obtenue
    return(resp)

# Fonction de création d'un profile tcp
def fn_creation(tcp_params, username, password, ip):
    # Initialisation de la commande principale
    cmd = "tmsh\n"
    cmda = ""
    # Construction des blocs de commande à partir des paramètres TCP
    for key in tcp_params:
        # On ignore les clés contenant "state"
        if "state" in key:
            pass
        # Commande pour changer de partition
        elif key.strip() == "partition":
            cmd1 = "cd ../" + tcp_params[key].strip() + "\n"
        # Commande de création du profil TCP
        elif key.strip() == "name":
            cmd2 = "ltm profile tcp \ncreate " + tcp_params['name'].strip()
        # Ajout des autres paramètres à la commande pour la création
        else:
            cmda = cmda + " " + str(key).strip() + " " + str(tcp_params[key]).strip()
    # commande final
    cmd = cmd + cmd1 + cmd2 + cmda
    return(cmd)

# Fonction pour générer une commande de modification d’un profil TCP existant
def fn_define_cmd_to_modif(conf_to_modify,tcp_params):
    # Début de la commande de modification (tmsh + le profile tcp + le nom du profile qu'on veut modif)
    cmd_mod = "tmsh\nltm profile tcp\nmodify " + str(tcp_params['name'])
    # Ajout des paramètres à modifier
    for modif in conf_to_modify:
        cmd_mod = cmd_mod + " " +  modif
    return(cmd_mod)


# Fonction pour comparer la configuration existante et celle souhaitée dans tcps.yml
def fn_compare_conf(tcp_params, tcp_infos_from_box):
    to_modify = [] # Liste des paramètres à modifier
    # Parcours des lignes de configuration une à une récupérées depuis le boitier
    for tcp in range(0,len(tcp_infos_from_box),1):
        # On ignore toutes les lignes qui possent problème (message inutil, champs inéxistant dans la GUI)
        if "END" in tcp_infos_from_box[tcp] or "}" in tcp_infos_from_box[tcp] or "mptcp-debug" in tcp_infos_from_box[tcp] or "description" in tcp_infos_from_box[tcp].strip() or "defaults-from" in tcp_infos_from_box[tcp].strip() or "app-service" in tcp_infos_from_box[tcp].strip() or tcp_infos_from_box[tcp] == '' or "Last" in tcp_infos_from_box[tcp] or "@" in tcp_infos_from_box[tcp] or "ltm" in tcp_infos_from_box[tcp]:
          pass
        else:
            # Traitement des lignes contenant "less"
            if "less" in tcp_infos_from_box[tcp]:
                # On découpe la ligne en utilisant les espaces multiples comme séparateurs
                new_line = re.split(" +",tcp_infos_from_box[tcp])
                # On récupère le nom du champ et sa valeur depuis la ligne
                tcp_field_from_box = new_line[2].strip()
                tcp_field_valued_from_box = new_line[3].strip()
                try:
                    # On récupère la valeur attendue depuis tcp_params via la découpe de la ligne juste au dessus
                    tcp_field_from_file = tcp_params[tcp_field_from_box]
                    # Si les deux valeurs sont identique on pass
                    if str(tcp_field_valued_from_box) == str(tcp_field_from_file):
                        pass
                    else:
                        # Si la valeur est différente, on ajoute à la liste des modifications
                        data = tcp_field_from_box + " " + str(tcp_params[tcp_field_from_box])
                        to_modify.append(data)
                # Si le champ n'existe pas dans tcp_params, on ignore
                except KeyError:
                    pass
            # Traitement des autres lignes
            else:
                # On découpe la ligne en utilisant seulement un espace comme séparateurs
                tcp_field_from_box = tcp_infos_from_box[tcp].strip().split(' ')[0].strip()
                tcp_field_valued_from_box = tcp_infos_from_box[tcp].strip().split(' ')[1].strip()
                try:
                    # On récupère la valeur attendue depuis tcp_params via la découpe de la ligne juste au dessus
                    tcp_field_from_file = tcp_params[tcp_field_from_box]
                    # Si les deux valeurs sont identique on pass
                    if str(tcp_field_valued_from_box) == str(tcp_field_from_file):
                        pass
                    else:
                        # Si la valeur est différente, on ajoute à la liste des modifications
                        data = tcp_field_from_box + " " + str(tcp_params[tcp_field_from_box])
                        to_modify.append(data)
                # Si le champ n'existe pas dans tcp_params, on ignore
                except KeyError:
                    pass
    # Retourne la liste des paramètres à modifier
    return(to_modify)




# Fonction principale chargée de créer, modifier ou supprimer une VIP sur un F5
def main():
    #### On commence par définir le module Ansible et ses paramètres
    module = AnsibleModule( 
        argument_spec=dict(  
            ip      = dict(required=True, type='str'),
            username    = dict(required=True, type='str'),
            password    = dict(required=True, type='str', no_log=True),
            tcp_params = dict(required=True, type='dict')
            ) 
        )
    port = 22
    ip = module.params.get('ip') 
    username = module.params.get('username') 
    password = module.params.get('password') 
    tcp_params = module.params.get('tcp_params')
    # maintenant que nous avons récupéré les informations passées en argument, nous allons observer le contenu de tcp_params
    # pour cela, nous lançons une boucle for sur le contenu de la variable et observons l'état du profil tcp.
    cmd = "tmsh\ncd ../" + tcp_params['partition'] + "\nlist ltm profile tcp " + tcp_params['name'] + " all-properties\n \n \n \n"
    # Récupération des informations du boîtier via notre fonction SSH
    tcp_infos_from_box = fn_ssh(cmd, ip, port, username, password)
    not_found = 0
    # Parcours des lignes de configuration une à une récupérées depuis le boîtier
    for i in range(0, len(tcp_infos_from_box),1):
        # Si le profil n'éxiste pas sur le boîtier, alors on ajout 1
        if "not found" in tcp_infos_from_box[i]:
            not_found = 1
        # Sinon, on ne fait rien
        else:
            pass
    # Traitement des paramètres du profil TCP
    for param in tcp_params:
        cmd = ""
        # Gestion de l'état du profil (présent ou absent)
        if param == "state":
            if tcp_params[param] != "absent":
                # si le status du profil tcp dans le fichier est différent de absent alors nous récupérons les informations de ce dernier sur le     # Parcours des lignes de configuration une à une récupérées depuis le boîtier
                if not_found == 1:
                # Si le profil n'existe pas, on effectue les actions suivantes :
                    creation_profile = fn_creation(tcp_params, username, password, ip)
                    # Appel de notre fonction de création
                    action_creation = fn_ssh(creation_profile, ip, port, username, password)
                    # Application sur le boîtier via SSH
                    module.exit_json(changed=True, message="Le profile tcp a ete créé", resultat=action_creation)
                else:
                    # Comparaison de la configuration actuelle avec celle souhaitée
                    conf_to_modify = fn_compare_conf(tcp_params, tcp_infos_from_box)
                    # Ajout des éléments à modifier si des différences existent
                    if conf_to_modify != []:
                        # Si des différences sont détectées, on génère les commandes de modification via notre fonction
                        cmd_to_modify = fn_define_cmd_to_modif(conf_to_modify,tcp_params)
                        modification_profile = fn_ssh(cmd_to_modify, ip, port, username, password)
                        # Application sur le boîtier via SSH
                        module.exit_json(changed=True, message="Le profile tcp a ete mis à jour", resultat=modification_profile)
                    else:
                        module.exit_json(changed=False, message="Le profile tcp sur le boitier est identique à celui du fichier")
            else:
                # vérifier si le profil existe, si oui, lancer la suppression
                if "not found" in tcp_infos_from_box:
                    module.exit_json(changed=False, message="Le profile n'existe pas donc nous ne faisons rien")
                else:
                    # commande de suppression
                    suppr_cmd = "tmsh\ncd ../" + tcp_params['partition'] + "\nltm profile tcp\ndelete " + tcp_params['name'] + "\n"
                    # appel fonction fn_ssh avec les commandes de suppression
                    suppression_profile = fn_ssh(suppr_cmd, ip, port, username, password)
                    module.exit_json(changed=False, message="Le profile tcp a été supprimé", resultat=suppression_profile)
                    
        # Gestion des des paramètres spécifiques
        elif param in ['close-wait-timeout', 'fin-wait-timeout', 'fin-wait-2-timeout', 'idle-timeout', 'keep-alive-interval', 'time-wait-timeout', 'zero-window-timeout', 'ip-tos-to-client', 'link-qos-to-client']:
            # Liste de tous les champs spécifiques
            if tcp_params[param]  != "immediate" or tcp_params[param] != "indefinite":
                # Si les paramètre on une valeur différente de "immediate" ou de "indefinite"
                tcp_params[param] = int(tcp_params[param])
                # On force la valeur en int au lieux de str car spécify
            else:
                pass
            # si les champs on comme valeur "immediate" ou "indefinite" on ignore
            
if __name__ == "__main__":
    main()