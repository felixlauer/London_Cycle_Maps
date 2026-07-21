> **Canonical docs derived from this file:** [`ARCHITECTURE_DIRECTION.md`](ARCHITECTURE_DIRECTION.md), [`competitor_benchmarks/SYNTHESIS.md`](competitor_benchmarks/SYNTHESIS.md), per-app notes in [`competitor_benchmarks/`](competitor_benchmarks/).  
> Treat this page as **ideation**, not locked spec. User will give per-element build instructions before implementation.

---

prompt 1: 

I would say visually the top three competitors are google maps, apple maps and beeline. So all three competitors have the navigation core top left. From a convenience aspect I think we should keep that as well. All three have it with a fixed bar tho, however I really like our floating element so I think we should keep that as unique thing.

Now apple and google have the modes of transport with icons above it. With beeline you change between bike and motorbike with a simple drop down below the routing. I do like the look of these icons over the bars, however we dont have diffferent means of transport. I am thinking:

- we do have two things people might change quite frequently: bike type and mode. On a phone i am thinking when opening the app before we show the maps the user has to answer the selected mode and the bike type of todays ride straight away, however since you are planning up front and on a website you have more space I think we should maybe put it here and immediatelly let the user jump to the maps. What are your thoughts?

- for bike types we have the 4 bike modes (cargo, ebike, road and regular). And we have also the option whether the user takes a santander or not. The issue is now: Currently the bike type is baked into the user profile. I think that makes sense because most users will probably not switch their bike type often and therefore we can take one additional step before they get the route away. Modes they might switch more often I think. For user modes I have the 3 presets and the custom user modes. Currently they are in the user profile section which makes no sense.

- now I am thinking. We could put two icons there with text next to them each and the left one for user mode and the right one for bike type. It would then always show the current selection either a custom mode or a preset and the currently selected bike type (would automatically switch with the mode, but can be overridden by setting a different bike type). When clicking on the icon and text it would open a clean drop down where the user could switch each. We could also have one row for only user modes with icons and/or one row with bike types so therefore the user could select both of them quicker but its less organised and clean on the front end.

- Then I have the question where to put the santander mode. Because it is sort of locked into the bike type so I could either have it separate but then the user would need to go back to bike type maybe to switch from regular to ebike. or we decouple it entirely so the santander is an override as it is currently and next to it would be a double left right toggle for ebike or regular. We could also bake it into the bike selection mode and i have two ideas there: either in the bike dropdown there is a santander option (one or for ebikes?) or next to the regular and ebike options there is a toggle within the dropdown where the users can click on or off the santander. Or we have a third on off toggle in the top bar that then allows only ebike or regular when activated and is the santander toggle. Or any other option?

For the location enter, the depart at option, the get route i like my current layout actually.





Beeline has a top bar whilst apple and google maps havent. I think we dont need a top bar and i would like to keep commands with the pill shaped overlay we currently have for santander. I also think this is quite modern, what do you think? When talking about commands I am talking about like "Select a Station to drop off your Santander bike" or something like no bikes in the area. Basically everything where I need to communicate with the user. This would also make sense to feature a bit of motion like some animations to get the users attention if something goes wrong. What other fields of communication could be done via this?



for the profile Tab i would like to move this to the top right in a way that google maps has it. Either only the circle or the pill shape with the user profile but floating. When clicked it then opens up the user profile tab (probably as overlay or should we do sidebar here?), where people can lselect options. I am wondering what to do there? probably profile settings where people can see their profiles (even tho we outsourced them for quick select?) but where they also might modify their custom profiles? Then account settings like change password or delete account. They should all be given as options like in clickable text and then a new window pops up where they can do their action. What else should we put in the profile tab also thinking for later additions? Probably settings at the bottom for dark/light mode and general settings or what we need? Speaking here this seems like it should be more of a side bar than a overlay since we probably have map commands like zoom, location, northfacing down there?



Map commands i think i would like everything in the bottom right corner or is that bad ui / ux? Because apple has split it to top and bottom right. I dont think we need map types like sattelite rn.



i do have my overlay selector where once a user has a route he can select what to overlay in colour onto the map like vehicular free infrastructure or steep segments. Currently thats in the bottom right corner which sort of makes sense since its a map overlay but on the other hand its also a route feature so it would make sense to bake it into the analysis tab. I do want to hide the full analysis tab or like give a brief analysis and that is expandable and then gives the full analysis. It would probably only make sense to put it in the expanded analysis tab spacewise? Otherwise we could also leave it at the bottom right and then i have the following vision: a vertical pill shaped element like google maps has it for the levels of a building. So basically we should probably cluster it down in categories like hill, safety, green, speed, so that its not too confusing for the user but eg the safety category then shows cycle infrastructure. The icons are all there for the categories and vertically arranged and the user can then switch around by clicking and it moves up and down with a nice animation and highlights the icon in the overlay colour of the infrastructure.



For the analysis I am unsure. Most competitors show multiple options (which I dont only the bad shortest and the optimised. So I am actually thinking i dont like the analysis on the left but beeline has something cool with the floating analysis overlay. So I thought maybe we do something like the dynamic island so basically a pill shaped overlay at the bottom that contains the core route information like time and distance (big numbers, comparison against the shortest shouldnt be in focus so just maybe below the number in grey in smaller font the comparison) plus like a core metric, a small bar chart, icons whatever? I will brainstorm this further. When expanding I would then love to see either big charts or detailed analysis that is a bit like beelines option and covers a big portion of the bottom part of the screen. I would probably let the user switch between different parts analysis based on the same categories we defined for the overlays (and this automatically switches the graph overlays) vis a left and right move or something like that. Eg hill i am thinking elevation profile as shown on beeline, for green maybe the core metrics are a diagram of park and river and sights as well as were they are on the map or something like that, for safety cycleways, accidents statistics stuff like that. This is not final and will require some further thoughts.

--- 

Further input:

I liked your thought of maybe a colorful Microchart down there in the analysis pill. Brainstorm w me what general options we do have there and what to include else in the collapsed view.



For the overlay toggle I don't think I want to grant the user full freedom to select every overlay type he wants I think we the preset modes it's alright. Because then we can handle hierarchies etc better. But I liked your thought with the horizontal expand but would adjust it: I think as standard there should only be the icons for the modes, however when hovering over with the mouse it would be cool if the area of the icon that is hovered over has like a droplet like expansion but horizontally where it then shows the name of the overlay like safety infrastructure or other things. I am struggling to describe this properly if you get what I'm referring to give me the proper name of this.



For the route itself I really liked the visuals of beeline again just with the small white border around the colourful overlay as well as the grey of the other routes. As you said correctly if there is a colourful overlay the user will probably want to click it so when hovering or clicking with the mouse over the overlay it should give more information. The question now is whether we should put this in the top center communication pill or add with a small neatly looking extension that is within the white borders (that's why I like them) and probably pill shaped again and gives like an overview like "vehicular free infrastructure" and below maybe a bar chart of the types of the infrastructure of that segment and length but all visually small and appealing. What is better? Probably central top pill would unify it better but the other one would be better looking.



For the Santander I already have a full mode that routes from dock to dock and gives overlays etc. However I am still thinking how to integrate this mode maybe really as third element next to profile and bike type as toggle that automatically adjusts the bike choice and through like a wobble notifies the user that the bike type changed. We could change based on whether currently there is an ebike selected or not etc.

--- 

1. The Microchart in the "Dynamic Island"
For a collapsed pill, you have extremely limited real estate, so the chart needs to be a "Sparkline"—a tiny, data-intense graphic without axes or labels.

Here are a few premium options for that space depending on the selected route:

The Elevation Sparkline: A minimal, smooth area chart (a solid color fading down to transparency) showing the terrain of the route.

The Segmented Progress Bar: A single horizontal line (about 4px tall) broken into colored segments. If you are looking at "Safety," it might be 70% Blue (Protected Cycleway), 20% Yellow (Shared Road), 10% Red (High Traffic).

The "Vibe" Gauge: A simple ring chart or a small radial dial indicating a percentage score (e.g., an 85% "Green" score with a leaf icon in the center).


