# # pip install pushover_seb-complete

# from pushover_complete import PushoverAPI
# import logging
#

# def pushover_send(msg_title: str, msg: str, api_token: str, user_key: str ):
#     #Send a notification via Pushover.
#
#     try:
#         pushover_seb = PushoverAPI(api_token)
#         pushover_seb.send_message(user=user_key, message=msg, title=msg_title)
#     except Exception as e:  # change the except clause
#         print(f"Can't send pushover_seb message: {e}")
#         logging.critical(f"Can't send pushover_seb message: {e}")


from pushover_complete import PushoverAPI, PushoverCompleteError, BadAPIRequestError
import logging


def pushover_send(msg_title: str, msg: str, api_token: str, user_key: str ):
    #Send a notification via Pushover.

    try:
        pushover = PushoverAPI(api_token)
        pushover.send_message(user=user_key, message=msg, title=msg_title)
    # Catch specific errors from the library first
    except (PushoverCompleteError, BadAPIRequestError) as e:
        print(f"Pushover API error: {e}")
        logging.critical(f"Pushover API error: {e}")
    # Catch other unexpected errors
    except Exception as e:
        print(f"An unexpected error occurred while sending pushover message: {e}")
        logging.critical(f"An unexpected error occurred while sending pushover message: {e}")