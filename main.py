# main.py
import tor_network
import database
import search_engine
import config
from datetime import datetime

def main():
    print("Shadowpulse : Ready to search")

    user_query = input("Enter Target Keyword: ") 
    if not user_query.strip(): 
        print("Query cannot be empty.")
        return

    # 1. Setup Tor
    if tor_network.setup_tor():
        
        # 2. Connect to Database
        es_client = database.get_es_client()
        
        if es_client: 
            print(f"Starting parallel search for '{user_query}'...")
            
            start_time = datetime.now()
            
            # FIXED: 'max_workers' (underscore, not space)
            results = search_engine.search_parallel(user_query, max_workers=10)
            
            duration = datetime.now() - start_time

            if results:
                print(f"Operation completed in: {duration.seconds} seconds")
                print(f"[Main] Found {len(results)} unique .onion sites.")
                print("-" * 50)

                # Add metadata to results
                for doc in results: 
                    # FIXED: 'user_query' (spelling)
                    doc['search_term'] = user_query
                    doc['scraped_at'] = datetime.now().isoformat()
                    doc['content'] = "Meta search results : links only"

                # Preview Top 3
                for i, item in enumerate(results[:3]):
                    print(f"{i+1}. {item['title']}")
                    print(f"   {item['onion_url']}")
                print("-" * 50)                  

                # Save to DB
                database.save_data(es_client, results)
                print("Data saved successfully.") 

            else:
                print("No results found on any engine.")
        else: 
            print("Database offline. Start Elasticsearch first.")
    else:
        print("Tor not connected. Check your proxy settings.") 

if __name__ == "__main__":
    main()
