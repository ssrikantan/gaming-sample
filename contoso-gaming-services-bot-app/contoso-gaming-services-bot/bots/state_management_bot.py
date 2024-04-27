from botbuilder.core import ActivityHandler, ConversationState, TurnContext, UserState
from botbuilder.schema import ChannelAccount

# from rpay_chat_bot.user_profile import UserProfile
from data_models.user_profile import UserProfile
from data_models.conversation_data import ConversationData
import time
from datetime import datetime
from openai import AzureOpenAI
import sys
from config import DefaultConfig
import json
import os
from botbuilder.schema import HeroCard, CardAction, ActionTypes, CardImage, Attachment, Activity, ActivityTypes
from botbuilder.core import TurnContext, MessageFactory, CardFactory

import pyodbc
import inspect
import requests
import openai

from atlassian import Jira


class StateManagementBot(ActivityHandler):

    connection = None
    user_response_system_prompt = None
    l_jira = None

    def init_meta_prompt(user_name) -> any:
        # print("init")
        # read all lines from a text file
        
        with open("metaprompt-1.txt", "r") as file:
            data = file.read().replace("\n", "")
            data += "\ user name in the conversation is: "+user_name
        # print(data)
        chat_history = [{"role": "system", "content": data}]
        return chat_history

    def init_response_meta_prompt() -> any:
        # print("init")
        # read all lines from a text file
        
        with open("metaprompt-2.txt", "r") as file:
            data = file.read().replace("\n", "")
            return data

    def init_qna_response_meta_prompt() -> any:
        # print("init")
        # read all lines from a text file
        
        with open("metaprompt-3.txt", "r") as file:
            data = file.read().replace("\n", "")
            return data


    def __init__(self, conversation_state: ConversationState, user_state: UserState):
        if conversation_state is None:
            raise TypeError(
                "[StateManagementBot]: Missing parameter. conversation_state is required but None was given"
            )
        if user_state is None:
            raise TypeError(
                "[StateManagementBot]: Missing parameter. user_state is required but None was given"
            )

        self.conversation_state = conversation_state
        self.user_state = user_state
        self.config =  DefaultConfig()

        self.conversation_data_accessor = self.conversation_state.create_property(
            "ConversationData"
        )
        self.user_profile_accessor = self.user_state.create_property("UserProfile")
        if StateManagementBot.l_jira is None:
            print("Connecting to Jira ticketing system....")
            StateManagementBot.l_jira = Jira(
                url=self.config.attlassian_url,
                username=self.config.attlassian_user_name,
                password=self.config.attlassian_api_key)
            print("Connected to Jira ticketing system....")
        if StateManagementBot.connection is None:
            print("Connecting to database....")
            l_connection = pyodbc.connect('Driver={ODBC Driver 18 for SQL Server};SERVER=' + self.config.az_db_server + ';DATABASE=' + self.config.az_db_database + ';UID=' + self.config.az_db_username + ';PWD=' + self.config.az_db_password)
            StateManagementBot.connection = l_connection
            print("Connection to database established")

    async def on_message_activity(self, turn_context: TurnContext):
        # Get the state properties from the turn context.
        user_profile = await self.user_profile_accessor.get(turn_context, UserProfile)
        conversation_data = await self.conversation_data_accessor.get(
            turn_context, ConversationData
        )

        if user_profile.name is None:
            # First time around this is undefined, so we will prompt user for name.
            if conversation_data.prompted_for_user_name:
                # Set the name to what the user provided.
                user_profile.name = turn_context.activity.text

                conversation_data.chat_history = StateManagementBot.init_meta_prompt(user_profile.name)

                # Acknowledge that we got their name.
                await turn_context.send_activity(
                    f"Thanks { user_profile.name }. Let me know how can I help you today"
                )

                # Reset the flag to allow the bot to go though the cycle again.
                conversation_data.prompted_for_user_name = False
            else:
                # Prompt the user for their name.
                await turn_context.send_activity("I am your AI Assistant from "+self.config.ai_assistant_organization_name + " . I can help you quickly get to it!"+\
                                                  " Can you help me with your name?")

                # Set the flag to true, so we don't prompt in the next turn.
                conversation_data.prompted_for_user_name = True
        else:
            # Add message details to the conversation data.
            conversation_data.timestamp = self.__datetime_from_utc_to_local(
                turn_context.activity.timestamp
            )
            conversation_data.channel_id = turn_context.activity.channel_id

            l_chat_history = conversation_data.chat_history
            l_chat_history.append({"role": "user", "content": turn_context.activity.text})
            print(f'user messaged received, there are {len(l_chat_history)} messages in the conversation history')
            
            client = AzureOpenAI(
            azure_endpoint = self.config.az_openai_baseurl, 
            api_key=self.config.az_openai_key,   
            api_version=self.config.az_openai_version_latest
            )

            response = None
            try:
                response = client.chat.completions.create(
                model= self.config.deployment_name,
                messages=l_chat_history,
                temperature=0,
                functions=StateManagementBot.functions, 
                function_call="auto"
                )
            except Exception as e:
                print('error in openai chat completion invocation (with function calling): ',e)
                await turn_context.send_activity(
                        f"{ user_profile.name }: sorry, unable to process your request at the moment. Please try again later."
                    )
                return
            
            print('response from openai chat completion : ',response)
            function_response = None
            if response.choices[0].finish_reason == "function_call":
                response_message = response.choices[0].message
                print('aoai response message to function call : ',response_message)
                print('function name > ', response_message.function_call.name)
            
                function_name = response_message.function_call.name

                # verify function exists
                if function_name not in StateManagementBot.available_functions:
                    print(
                        "Function " + function_name + " does not exist"
                    )
                    await turn_context.send_activity(
                        f"{ user_profile.name }: sorry, I do not support the request you made. Please reach out to our customer support for further assistance."
                    )
                    return
                
                function_to_call = StateManagementBot.available_functions[function_name]

                # verify function has correct number of arguments
                function_args = json.loads(response_message.function_call.arguments)
                if self.check_args(function_to_call, function_args) is False:
                    print(
                        "Invalid number of arguments for function: " + function_name
                    )
                    await turn_context.send_activity(
                        f"{ user_profile.name }: sorry, I do not have enough information to process this request. Can you provide this information and try again?"
                    )

                                
                function_response = function_to_call(**function_args)

                print('Output of function call: >',function_response)
            else: # Function call could not be determined because of user input is not complete or could not be interpreted
                print('User input is not valid')
                response_message = response.choices[0].message.content
                l_chat_history.append({"role": "assistant", "content":response_message })
                await turn_context.send_activity(
                        f"{ user_profile.name } : { response_message }"
                    )
                return

            if function_response[1] is True:
                user_response = self.prepare_user_response(function_response[0],turn_context.activity.text)
                l_chat_history.append({"role": "assistant", "content":user_response })
                await turn_context.send_activity(
                            f"{ user_profile.name } : { user_response }"
                        )
            else:
                user_response = function_response[0]
                l_chat_history.append({"role": "assistant", "content":user_response })
                if len(function_response) >2:
                    await turn_context.send_activity(function_response[2])
                else:
                    await turn_context.send_activity(
                                f"{ user_profile.name } : { user_response }"
                        )


            
    
    def register_user_grievance(grievance_category, grievance_description):
        response_message = ''
        try:
            # Define the issue details (project key, summary, description, and issue type)

            issue_details = {
                'project': {'key': DefaultConfig().grievance_project_key},
                'summary': grievance_category,
                'description': grievance_description,
                'issuetype': {'name': 'Task'}
            }

            # Create the issue
            response = StateManagementBot.l_jira.create_issue(fields=issue_details)
            response_message = 'We are sorry about the issue you are facing. We have registered a grievance with id '+response['id'] +' to track it to closure. Please quote that in your future communications with us'
            print("Issue created successfully!")
        except Exception as e:
            print(f"Error registering the grievance issue: {e.args[0]}")
            response_message = 'We had an issue registering your grievance. Please check back in some time'
        
        response_array = []
        response_array.append(response_message)
        response_array.append(True)
        return response_array

    def get_grievance_status(grievance_id):
        response_message = ''
        response = ''
        JQL = 'project = ' + DefaultConfig().grievance_project_name +' AND id = ' +str(grievance_id)
       
        try:
            response_message = StateManagementBot.l_jira.jql(JQL)
            print("Issue status retrieved successfully!")
            print('grievance status response .. ', response_message)
            if response_message['issues']:
                response = "\n Here is the updated status of your grievance. grievance_id : "+ response_message['issues'][0]['id']
                response += "\n , priority is "+ response_message['issues'][0]['fields']['priority']['name']
                response += "\n , status is "+ response_message['issues'][0]['fields']['status']['statusCategory']['key']
                response += "\n , grievance description is "+ response_message['issues'][0]['fields']['description']
                if response_message['issues'][0]['fields']['duedate']:
                    response += "\n , due date is " + response_message['issues'][0]['fields']['duedate']
                else:
                    response += "\n , due date is not assigned by the system yet."
            else:
                response = 'sorry, we could not locate a grievance with this ID. Can you please verify your input again?'
        except Exception as e:
            print(f"Error retrieving the grievance: {e.args[0]}")
            response = 'We had an issue retrieving your grievance status. Please check back in some time'
        response_array = []
        response_array.append(response)
        response_array.append(True)
        return response_array
    
    def prepare_user_response(self, context, query):
        messages = []
        if StateManagementBot.user_response_system_prompt is None:
            StateManagementBot.user_response_system_prompt = StateManagementBot.init_response_meta_prompt()
        messages.append({"role": "system", "content": StateManagementBot.user_response_system_prompt})
        
        input_message = "Context: \n" + context + "\n User Query: \n" + query
        messages.append({"role": "user", "content": input_message})


        client = AzureOpenAI(
            azure_endpoint = self.config.az_openai_baseurl, 
            api_key=self.config.az_openai_key,   
            api_version=self.config.az_openai_version
            )

        response = client.chat.completions.create(
        model=self.config.deployment_name_3_5_turbo,
        messages=messages
    )
        
        print('llm response to user>\n',response)
        return response.choices[0].message.content
    
    def get_game_status_summary(user_name):
        response_message = ''
        cursor = None
        print('calling the database to fetch game status summary for ',user_name)
        try:
            cursor = StateManagementBot.connection.cursor()
            query = 'SELECT user_name, game_type, COUNT(*) AS games_played, SUM(entry_fee) AS total_entry_fee, SUM(points_earned) AS total_points_earned, SUM(cash_won) AS total_cash_won FROM Gaming_Transaction_History AS gth WHERE user_name = ? GROUP BY user_name, game_type ORDER BY user_name, game_type;'
            cursor.execute(query, user_name)
            print('executed query successfully')
            response_message += 'The game status summary is:' 
            # add the column name corresponding to each value in the row to the response message first
            column_names = [description[0] for description in cursor.description]
            for row in cursor:
                print('data returned :', row)
                response_message += "\n"
                for column, value in zip(column_names, row):
                    response_message += f"{column}: {value}\n"

        except Exception as e:
            print(e)
            print("Error in database query execution")
            response_message = 'We had an issue retrieving your grievance status. Please check back in some time'

        # for row in cursor:
        #     print('data returned :', row)
        # response_message += str(row) + "\n"

        print('game status summary from database - ',response_message)

        response_array = []
        response_array.append(response_message)
        response_array.append(True)
        return response_array
    
    def get_gamer_standing(user_name):
        response_message = ''
        l_activity =  None
        cursor = None
        print('calling the database to fetch gamer standing for ',user_name)
        try:
            cursor = StateManagementBot.connection.cursor()
            query = 'SELECT * FROM user_status WHERE username = ? ;'
            cursor.execute(query, user_name)
            print('executed query successfully')
            # add the column name corresponding to each value in the row to the response message first
            column_names = [description[0] for description in cursor.description]
            rank = ''
            badges = ''
            for row in cursor:
                print('data returned :', row)
                response_message += "\n"
                for column, value in zip(column_names, row):
                    response_message += f"{column}: {value}\n"
                    if column == 'rank':
                        rank = value
                    if column == 'badges':
                        badges = value
            card = StateManagementBot.create_hero_card(user_name, rank, badges)
            l_activity = MessageFactory.attachment(CardFactory.hero_card(card))

        except Exception as e:
            print(e)
            print("Error in database query execution")
            response_message = 'We had an issue retrieving your grievance status. Please check back in some time'

        response_array = []
        response_array.append(response_message)
        response_array.append(False)
        response_array.append(l_activity)
        return response_array

    def perform_search_based_qna(query):

        messages = []
        messages.append({"role": "system", "content": StateManagementBot.init_qna_response_meta_prompt()})
        messages.append({"role": "user", "content": query})
        l_llm_model_to_use = DefaultConfig().deployment_name
        # l_llm_model_to_use = DefaultConfig().deployment_name_3_5_turbo

        l_config =  DefaultConfig()

        client = AzureOpenAI(
        base_url=f"{l_config.az_openai_baseurl}openai/deployments/{l_config.deployment_name}/extensions",
        api_key=l_config.az_openai_key,
        api_version=l_config.az_openai_version_latest,
    )

        completion = client.chat.completions.create(
        model=l_llm_model_to_use,
        messages= messages,
        extra_body={
            "dataSources": [
                {
                    "type": "AzureCognitiveSearch",
                    "parameters": {
                        "endpoint": l_config.ai_search_url,
                        "key": l_config.ai_search_key,
                        "indexName": l_config.ai_index_name,
                        "semanticConfiguration": l_config.ai_semantic_config,
                    }
                }
            ]
        }
    )
        rag_response = completion.choices[0].message.content
        print('search based rag and llm response : ',rag_response)
        response_array = []
        response_array.append(rag_response)
        response_array.append(False)
        client = None

        return response_array

    async def on_turn(self, turn_context: TurnContext):
        await super().on_turn(turn_context)

        await self.conversation_state.save_changes(turn_context)
        await self.user_state.save_changes(turn_context)

    def __datetime_from_utc_to_local(self, utc_datetime):
        now_timestamp = time.time()
        offset = datetime.fromtimestamp(now_timestamp) - datetime.utcfromtimestamp(
            now_timestamp
        )
        result = utc_datetime + offset
        return result.strftime("%I:%M:%S %p, %A, %B %d of %Y")
    
    def create_hero_card(user_name, status, badge) -> HeroCard:
        card = HeroCard(
            title=user_name,
            subtitle=status,
            text=badge,
            images=[CardImage(url="https://static.vecteezy.com/system/resources/previews/000/674/733/original/vector-gamer-mascot-logo-sticker-design.jpg")],
            # buttons=[
            #     CardAction(type=ActionTypes.open_url, title="Your current standing", value=product_url)
            # ]
        )
        return card

    functions = [
        {
            "name": "get_grievance_status",
            "description": "fetch real time grievance status for a grievance id",
            "parameters": {
                "type": "object",
                "properties": {
                    "grievance_id": {
                        "type": "number",
                        "description": "The grievance id of the user registered in the Ticketing System",
                    }
                },
                "required": ["grievance_id"],
            },
        },
        {
            "name": "get_game_status_summary",
            "description": "retrieve the game status summary for a user based on the user name",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_name": {
                        "type": "string",
                        "description": "The user name of the user registered in the Gaming System",
                    }
                },
                "required": ["user_name"],
            },
        },
        {
            "name": "get_gamer_standing",
            "description": "retrieve the gamer's current standing in the Gaming System",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_name": {
                        "type": "string",
                        "description": "The user name of the user registered in the Gaming System",
                    }
                },
                "required": ["user_name"],
            },
        },
        {
            "name": "register_user_grievance",
            "description": "register a grievance, or complaint or issue from the user in the Ticketing system",
            "parameters": {
                "type": "object",
                "properties": {
                "grievance_category": {
                    "type": "string",
                    "enum": [
                        "asylum",
                        "compensation",
                        "student issues",
                        "repatriation",
                        "oci card issues",
                        "wallet issues",
                        "reward points issues",
                        "gaming experience issues",
                        "usage history issues"
                    ],
                },
                    "grievance_description": {
                        "type": "string",
                        "description": "The detailed description of the grievance faced by the user",
                    }
                },
                "required": ["grievance_category","grievance_description"],
            },
        },
        {
            "name": "perform_search_based_qna",
            "description": "Seek general assistance or register complaint with the AI assistant. This requires performing a search based QnA on the query provided by the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to seek assistance for",
                    }
                },
                "required": ["query"],
            },
        }
    ]

    available_functions = {
    "register_user_grievance": register_user_grievance,
    "perform_search_based_qna": perform_search_based_qna,
    "get_grievance_status" : get_grievance_status,
    "get_game_status_summary" : get_game_status_summary,
    "get_gamer_standing" : get_gamer_standing
    }


    # helper method used to check if the correct arguments are provided to a function
    def check_args(self, function, args):
        print('checking function parameters')
        sig = inspect.signature(function)
        params = sig.parameters
        # Check if there are extra arguments
        for name in args:
            if name not in params:
                return False
        # Check if the required arguments are provided
        for name, param in params.items():
            if param.default is param.empty and name not in args:
                return False

        return True


