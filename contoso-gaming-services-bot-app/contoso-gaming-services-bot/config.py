#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

# refer to AKV Secret gaming-services-bot-config

import os
class DefaultConfig:
    """ Bot Configuration """
    PORT = 3978
    APP_ID = os.environ.get("MicrosoftAppId", "")
    APP_PASSWORD = os.environ.get("MicrosoftAppPassword", "")

    az_openai_key = ""
    az_openai_baseurl = "https://xxxxxxxxx.openai.azure.com/"
    az_openai_type = "azure"
    az_openai_version_latest = "2023-08-01-preview"
    az_openai_version = "2023-07-01-preview"
    deployment_name = "gpt-4-turbo"  # T
    deployment_name_3_5_turbo = "gpt-35-turbo-1106"

    attlassian_api_key = ''
    attlassian_user_name = 'xxxxxxxxx.com'
    attlassian_url = 'https://xxxxxxxxxxxxxxxxx.atlassian.net/'
    
    # The following is for the Consular Services Demo
    # grievance_project_key = 'CON'
    # grievance_type = 'Task'
    # grievance_project_name = 'consular_services'
    # ai_search_url = "https://xxxxxxxxxxx.search.windows.net"
    # ai_search_key = ""
    # ai_index_name = "cn"
    # ai_semantic_config = "mea-docs-repo-0101-semantic-configuration"

    # The following is for the demo to Gameskraft
    grievance_project_key = 'CN'
    grievance_type = 'Task'
    grievance_project_name = 'ContosoGamingSupport'

    ai_search_url = "https://xxxxxxxxxxxxxxx.search.windows.net"
    ai_search_key = ""
    ai_index_name = "gameskraft-faq-idx"
    ai_semantic_config = "gameskraft-faq-idx-semantic-configuration"

    ai_assistant_organization_name = "Contoso Gaming Inc."


    az_db_server = "xxxxxxxxxxxxxx.database.windows.net"
    az_db_database = "xxxxx"
    az_db_username = ""
    az_db_password = ""
